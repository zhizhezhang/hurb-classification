<template>
  <main class="recognition-page">
    <section class="recognition-paper" aria-label="智能识别">
      <div class="recognition-paper-content">
        <label class="image-picker">
          <input
            class="image-input"
            type="file"
            accept="image/jpeg,image/png,.jpg,.jpeg,.png"
            aria-label="选择图片进行识别"
            @change="selectImage"
          />
          <img v-if="previewUrl" :src="previewUrl" alt="已选择的图片" />
          <span v-else>选择图片</span>
        </label>

        <Transition name="poem" mode="out-in" :css="status === 'idle'">
          <p v-if="status === 'idle'" :key="poemIndex" class="recognition-poem">
            <span class="recognition-poem-line">{{ poems[poemIndex].first }}</span>
            <span class="recognition-poem-line">{{ poems[poemIndex].second }}</span>
          </p>
        </Transition>

        <p v-if="status === 'loading'" class="recognition-state" role="status">正在识别…</p>
        <p v-if="status === 'error'" class="recognition-state recognition-error" role="alert">
          {{ errorMessage }}
        </p>
        <section v-if="status === 'low-confidence'" class="recognition-state recognition-error recognition-low-confidence" role="status" aria-label="识别失败">
          <h2>识别失败</h2>
          <p>{{ LOW_CONFIDENCE_MESSAGE }}</p>
        </section>

        <template v-if="status === 'success' && prediction">
          <section class="recognition-result" aria-label="识别结果">
            <h2 class="section-title">识别结果</h2>
            <div class="top-result">
              <div class="top-result-text">
                <strong class="predicted-name">{{ prediction.predicted_class }}</strong>
                <div class="confidence">
                  <span>置信度</span>
                  <strong>{{ formatPercent(prediction.confidence) }}</strong>
                </div>
              </div>
              <img
                v-if="herb?.image_url"
                class="herb-illustration"
                :src="herb.image_url"
                :alt="`${herb.name}插画`"
              />
            </div>
          </section>

          <section v-if="herb?.recognition_intro || herbError" class="herb-intro" aria-label="药材简介">
            <h2 class="section-title">药材简介</h2>
            <p v-if="herb?.recognition_intro">{{ herb.recognition_intro }}</p>
            <p v-else class="recognition-error" role="alert">{{ herbError }}</p>
          </section>

          <section class="top-three" aria-label="前三预测">
            <h2 class="section-title">Top-3</h2>
            <ol>
              <li v-for="(item, index) in sortedTop3" :key="item.class_name">
                <span class="top-three-rank">{{ index + 1 }}.</span>
                <span class="top-three-name">{{ item.class_name }}</span>
                <span class="top-three-track" aria-hidden="true">
                  <span
                    class="top-three-fill"
                    :style="{ width: `${safeProbability(item.probability) * 100}%` }"
                  ></span>
                </span>
                <strong>{{ formatTop3Percent(item.probability) }}</strong>
              </li>
            </ol>
          </section>
        </template>
      </div>
    </section>
  </main>
  <DeepSeekChat :herb-id="status === 'success' && recognizedHerbId ? recognizedHerbId : null" />
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getHerb, getHerbs, predictImage } from '../api/index.js'
import DeepSeekChat from '../components/recognition/DeepSeekChat.vue'
import { isRecognitionSuccessful, LOW_CONFIDENCE_MESSAGE } from '../utils/recognitionStatus.js'
import '../styles/recognition.css'

const poems = [
  { first: '一叶知本草，', second: '一眼辨岐黄。' },
  { first: '一镜窥百草，', second: '一卷识灵枢。' },
  { first: '瞬息识草木，', second: '指尖阅千金。' },
]

const poemIndex = ref(0)
const status = ref('idle')
const previewUrl = ref('')
const prediction = ref(null)
const herb = ref(null)
const recognizedHerbId = ref(null)
const errorMessage = ref('')
const herbError = ref('')
const sortedTop3 = computed(() =>
  [...(prediction.value?.top3 ?? [])].sort((a, b) => b.probability - a.probability),
)

let poemTimer
let selectionVersion = 0

function stopPoem() {
  if (poemTimer) {
    clearInterval(poemTimer)
    poemTimer = undefined
  }
}

onMounted(() => {
  poemTimer = setInterval(() => {
    poemIndex.value = (poemIndex.value + 1) % poems.length
  }, 5000)
})

onBeforeUnmount(() => {
  selectionVersion += 1
  stopPoem()
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

function formatPercent(value) {
  return `${(value * 100).toFixed(2)}%`
}

function safeProbability(value) {
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0
}

function formatTop3Percent(value) {
  return `${(safeProbability(value) * 100).toFixed(2)}%`
}

function fileError(file) {
  if (file.size === 0) return '图片文件为空，请重新选择。'
  if (file.size > 10 * 1024 * 1024) return '图片不能超过10 MiB，请重新选择。'
  const knownType = file.type === 'image/jpeg' || file.type === 'image/png'
  const knownExtension = !file.type && /\.(jpe?g|png)$/i.test(file.name)
  if (!knownType && !knownExtension) return '请选择JPEG或PNG图片。'
  return ''
}

function requestError(error) {
  const code = error.response?.status
  if (code === 400) return '图片文件为空，请重新选择。'
  if (code === 413) return '图片超过大小或像素限制，请重新选择。'
  if (code === 415) return '仅支持JPEG或PNG图片。'
  if (code === 422) return '图片无法读取，请重新选择。'
  if (code === 503) return '识别服务暂不可用，请稍后重试。'
  if (!error.response) return '网络连接失败，请稍后重试。'
  return '识别失败，请重新选择图片。'
}

async function selectImage(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return

  const currentVersion = ++selectionVersion
  stopPoem()
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  prediction.value = null
  herb.value = null
  recognizedHerbId.value = null
  herbError.value = ''
  errorMessage.value = ''

  const validationError = fileError(file)
  if (validationError) {
    status.value = 'error'
    errorMessage.value = validationError
    return
  }

  previewUrl.value = URL.createObjectURL(file)
  status.value = 'loading'

  try {
    const predictionResponse = await predictImage(file)
    if (currentVersion !== selectionVersion) return
    const result = predictionResponse.data.data
    if (!isRecognitionSuccessful(result.confidence)) {
      status.value = 'low-confidence'
      return
    }
    prediction.value = result

    try {
      const catalogResponse = await getHerbs()
      if (currentVersion !== selectionVersion) return
      const matched = catalogResponse.data.data.find(
        (entry) => entry.name === result.predicted_class,
      )
      if (matched) {
        recognizedHerbId.value = matched.id
        const herbResponse = await getHerb(matched.id)
        if (currentVersion !== selectionVersion) return
        herb.value = herbResponse.data.data
        if (!herb.value.recognition_intro) {
          herbError.value = '当前药材资料未返回简介，请重启后端服务后重试。'
        }
      } else {
        herbError.value = '暂未找到对应的药材资料。'
      }
    } catch {
      if (currentVersion !== selectionVersion) return
      herbError.value = '药材资料暂不可用。'
    }

    status.value = 'success'
  } catch (error) {
    if (currentVersion !== selectionVersion) return
    errorMessage.value = requestError(error)
    status.value = 'error'
  }
}
</script>
