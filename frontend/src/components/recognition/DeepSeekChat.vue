<template>
  <button
    v-if="!isOpen"
    ref="entryButton"
    class="chat-entry"
    type="button"
    aria-label="打开本草知识问答"
    @click="openChat"
  >
    向 灵枝本草助手 提问…
  </button>

  <Transition name="chat-slide">
    <section v-if="isOpen" class="chat-panel" role="dialog" aria-label="本草知识问答">
      <header class="chat-header">
        <h2>本草知识问答</h2>
        <button type="button" aria-label="关闭问答" @click="closeChat">关闭</button>
      </header>
      <div class="chat-modes" role="group" aria-label="问答模式">
        <button type="button" :aria-pressed="mode === 'knowledge'" @click="mode = 'knowledge'">本草知识库</button>
        <button type="button" :aria-pressed="mode === 'deepseek'" @click="mode = 'deepseek'">DeepSeek AI</button>
      </div>
      <div ref="messageArea" class="chat-messages" aria-live="polite">
        <div v-for="message in messages" :key="message.id" class="chat-message" :class="`chat-message--${message.role}`">
          <span class="chat-message-sender">{{ message.role === 'assistant' ? '灵枝本草助手' : '我' }}</span>
          <div class="chat-message-bubble">
            <div v-if="message.role === 'assistant'" class="chat-markdown" v-html="message.html"></div>
            <span v-else class="chat-message-text">{{ message.text }}</span>
            <div v-if="message.sources?.length" class="chat-sources">
              <strong>参考依据</strong>
              <ul>
                <li v-for="source in message.sources" :key="source.key">
                  [{{ source.key }}] {{ source.title }} · {{ source.herb_name }} · {{ fieldLabel(source.field) }}
                </li>
              </ul>
            </div>
            <button v-if="message.canSwitch" class="chat-switch" type="button" @click="switchToDeepSeek(message.question)">切换到DeepSeek AI</button>
          </div>
        </div>
        <p v-if="isSending" class="chat-pending" role="status">正在回复…</p>
        <p v-if="errorMessage" class="chat-error" role="alert">{{ errorMessage }}</p>
      </div>
      <form class="chat-form" @submit.prevent="sendMessage">
        <textarea
          ref="questionInput"
          v-model="question"
          aria-label="输入本草问题"
          rows="2"
          maxlength="2000"
          placeholder="向灵枝本草助手提问..."
        ></textarea>
        <button type="submit" :disabled="isSending || !question.trim()">发送</button>
      </form>
    </section>
  </Transition>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { askHerbalAdvisor, normalizeAdvisorResponse } from '../../api/index.js'
import { renderChatMarkdown } from '../../utils/renderChatMarkdown.js'

const props = defineProps({ herbId: { type: String, default: null } })
const isOpen = ref(false)
const isSending = ref(false)
const mode = ref('knowledge')
const question = ref('')
const messages = ref([])
const errorMessage = ref('')
const entryButton = ref(null)
const questionInput = ref(null)
const messageArea = ref(null)
let nextMessageId = 0
const fieldLabels = {
  name: '药材名称',
  appearance: '外貌特征',
  allusion: '本草典故',
  traditional_effects: '传统功效',
  recognition_intro: '识别简介',
  summary: '药材概述',
  source: '药材来源',
  medicinal_part: '药用部位',
}

function fieldLabel(field) {
  return fieldLabels[field] ?? field ?? '其他资料'
}

async function scrollToLatest() {
  await nextTick()
  if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight
}

async function openChat() {
  isOpen.value = true
  await nextTick()
  questionInput.value?.focus()
  scrollToLatest()
}

async function closeChat() {
  isOpen.value = false
  await nextTick()
  entryButton.value?.focus()
}

async function switchToDeepSeek(originalQuestion) {
  mode.value = 'deepseek'
  question.value = originalQuestion
  await nextTick()
  questionInput.value?.focus()
}

async function sendMessage() {
  const text = question.value.trim()
  if (!text || isSending.value) return
  const herbId = props.herbId
  const requestMode = mode.value
  question.value = ''
  errorMessage.value = ''
  messages.value.push({ id: ++nextMessageId, role: 'user', text, mode: requestMode })
  isSending.value = true
  scrollToLatest()

  try {
    const response = await askHerbalAdvisor(text, herbId, requestMode)
    const data = normalizeAdvisorResponse(response)
    messages.value.push({
      id: ++nextMessageId,
      role: 'assistant',
      html: renderChatMarkdown(data.answer),
      groundingStatus: data.groundingStatus,
      answerOrigin: data.answerOrigin,
      mode: requestMode,
      question: text,
      canSwitch: requestMode === 'knowledge' && data.groundingStatus === 'insufficient' && data.switchRecommended,
      sources: requestMode === 'knowledge' ? data.sources : [],
    })
  } catch (error) {
    errorMessage.value = error.response?.status === 503
      ? '问答服务暂不可用，请稍后重试。'
      : '发送失败，请稍后重试。'
  } finally {
    isSending.value = false
    scrollToLatest()
  }
}
</script>
