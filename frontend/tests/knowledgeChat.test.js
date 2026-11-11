import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { askHerbalAdvisor, normalizeAdvisorResponse } from '../src/api/index.js'
import { http } from '../src/api/http.js'
import { renderChatMarkdown } from '../src/utils/renderChatMarkdown.js'
import { isRecognitionSuccessful } from '../src/utils/recognitionStatus.js'

const builtIn = (key, herbId, herbName, field) => ({
  key, source_type: 'built_in', title: '灵枝本草内置药材资料',
  herb_id: herbId, herb_name: herbName, field,
})
const wrap = (data) => ({ data: { success: true, data: { answer: '回答', herb_id: null, model: 'deepseek-flash', ...data } } })

test('single and dual grounded answers retain only returned built-in sources in order', () => {
  const one = builtIn('S1', 'huangqi', '黄芪', 'appearance')
  const two = builtIn('S2', 'renshen', '人参', 'appearance')
  assert.deepEqual(normalizeAdvisorResponse(wrap({ grounding_status: 'grounded', sources: [one] })).sources, [one])
  assert.deepEqual(normalizeAdvisorResponse(wrap({ grounding_status: 'grounded', sources: [one, two] })).sources, [one, two])
})

test('insufficient, general, empty and legacy responses keep the answer without inventing sources', () => {
  const one = builtIn('S1', 'huangqi', '黄芪', 'appearance')
  for (const data of [
    { grounding_status: 'insufficient', answer_origin: 'local_guardrail', sources: [] },
    { grounding_status: 'ungrounded_legacy', answer_origin: 'model_general', sources: [] },
    { grounding_status: 'grounded', sources: [] },
    {},
  ]) {
    const normalized = normalizeAdvisorResponse(wrap(data))
    assert.equal(normalized.answer, '回答')
    assert.deepEqual(normalized.sources, [])
  }
  assert.deepEqual(normalizeAdvisorResponse(wrap({ grounding_status: 'insufficient', sources: [one] })).sources, [])
  assert.deepEqual(normalizeAdvisorResponse(wrap({ grounding_status: 'ungrounded_legacy', sources: [one] })).sources, [])
})

test('source metadata cannot relabel built-in material as an external authority', () => {
  const fake = { ...builtIn('S1', 'huangqi', '黄芪', 'appearance'), title: '中国药典原文' }
  assert.deepEqual(normalizeAdvisorResponse(wrap({ grounding_status: 'grounded', sources: [fake] })).sources, [])
})

test('chat API keeps its existing request body and propagates failures', async () => {
  const previous = http.defaults.adapter
  const requests = []
  http.defaults.adapter = async (config) => {
    requests.push({ url: config.url, body: JSON.parse(config.data) })
    return { data: wrap({}).data, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await askHerbalAdvisor('什么是本草？')
    await askHerbalAdvisor('它的外貌？', 'huangqi')
    await askHerbalAdvisor('黄芪的外貌？', 'huangqi', 'knowledge')
    await askHerbalAdvisor('写一首诗', null, 'deepseek')
    assert.deepEqual(requests, [
      { url: '/ai/chat', body: { message: '什么是本草？' } },
      { url: '/ai/chat', body: { message: '它的外貌？', herb_id: 'huangqi' } },
      { url: '/ai/chat', body: { message: '黄芪的外貌？', herb_id: 'huangqi', mode: 'knowledge' } },
      { url: '/ai/chat', body: { message: '写一首诗', mode: 'deepseek' } },
    ])
    http.defaults.adapter = async () => { throw { response: { status: 503 } } }
    await assert.rejects(askHerbalAdvisor('问题'), (error) => error.response.status === 503)
  } finally {
    http.defaults.adapter = previous
  }
})

test('explicit modes keep real sources and expose a switch only for local knowledge gaps', () => {
  const source = builtIn('S1', 'huangqi', '黄芪', 'appearance')
  const knowledge = normalizeAdvisorResponse(wrap({
    grounding_status: 'grounded', answer_origin: 'local_knowledge', sources: [source],
  }))
  assert.deepEqual(knowledge.sources, [source])
  assert.equal(knowledge.switchRecommended, false)
  const missing = normalizeAdvisorResponse(wrap({
    grounding_status: 'insufficient', switch_recommended: true, sources: [],
  }))
  assert.equal(missing.switchRecommended, true)
  assert.deepEqual(missing.sources, [])
  const model = normalizeAdvisorResponse(wrap({
    grounding_status: 'ungrounded_legacy', answer_origin: 'model_general', sources: [source],
  }))
  assert.deepEqual(model.sources, [])
  assert.match(renderChatMarkdown('**黄芪**'), /<strong>黄芪<\/strong>/)
})

test('mode switch preserves the draft and each request owns its mode and herb context', () => {
  const chat = readFileSync(new URL('../src/components/recognition/DeepSeekChat.vue', import.meta.url), 'utf8')
  assert.match(chat, /mode = ref\('knowledge'\)/)
  assert.match(chat, /mode\.value = 'deepseek'\s+question\.value = originalQuestion/)
  assert.match(chat, /const herbId = props\.herbId\s+const requestMode = mode\.value/)
  assert.match(chat, /askHerbalAdvisor\(text, herbId, requestMode\)/)
  assert.match(chat, /mode: requestMode,\s+question: text/)
  assert.match(chat, /sources: requestMode === 'knowledge' \? data\.sources : \[\]/)
  assert.match(chat, /:aria-pressed="mode === 'knowledge'"/)
  assert.match(chat, /:aria-pressed="mode === 'deepseek'"/)
  assert.doesNotMatch(chat, /messages\.value\s*=\s*\[\]/)
  assert.doesNotMatch(chat, /switchToDeepSeek\([^)]*\)[^{]*\{[^}]*sendMessage\(/s)
})

test('recognition threshold and current image state gate the chat context', () => {
  assert.equal(isRecognitionSuccessful(0.5999), false)
  assert.equal(isRecognitionSuccessful(0.6), true)
  const view = readFileSync(new URL('../src/views/RecognitionView.vue', import.meta.url), 'utf8')
  assert.match(view, /status === 'success' && recognizedHerbId \? recognizedHerbId : null/)
  assert.match(view, /prediction\.value = null\s+herb\.value = null\s+recognizedHerbId\.value = null/)
  assert.match(view, /const matched = catalogResponse\.data\.data\.find\([\s\S]*entry\.name === result\.predicted_class/)
  assert.match(view, /if \(currentVersion !== selectionVersion\) return\s+const matched = [\s\S]*if \(matched\) \{\s+recognizedHerbId\.value = matched\.id/)
  assert.match(view, /currentVersion !== selectionVersion/g)
})

test('actual chat HTTP bodies follow mapped recognition context across modes and image changes', async () => {
  const previous = http.defaults.adapter
  const bodies = []
  http.defaults.adapter = async (config) => {
    bodies.push(JSON.parse(config.data))
    return { data: wrap({}).data, status: 200, statusText: 'OK', headers: {}, config }
  }
  try {
    await askHerbalAdvisor('有什么功效？', 'huangqi', 'knowledge')
    await askHerbalAdvisor('识别结果有什么功效？', 'dongchongxiacao', 'knowledge')
    await askHerbalAdvisor('有什么功效？', 'dongchongxiacao', 'deepseek')
    await askHerbalAdvisor('黄芪有什么传统功效？', 'dongchongxiacao', 'deepseek')
    await askHerbalAdvisor('有什么功效？', null, 'knowledge')
    await askHerbalAdvisor('你好。', null, 'deepseek')
    assert.deepEqual(bodies, [
      { message: '有什么功效？', herb_id: 'huangqi', mode: 'knowledge' },
      { message: '识别结果有什么功效？', herb_id: 'dongchongxiacao', mode: 'knowledge' },
      { message: '有什么功效？', herb_id: 'dongchongxiacao', mode: 'deepseek' },
      { message: '黄芪有什么传统功效？', herb_id: 'dongchongxiacao', mode: 'deepseek' },
      { message: '有什么功效？', mode: 'knowledge' },
      { message: '你好。', mode: 'deepseek' },
    ])
  } finally {
    http.defaults.adapter = previous
  }
})

test('sources use escaped Vue text nodes and existing Markdown safety remains active', () => {
  const chat = readFileSync(new URL('../src/components/recognition/DeepSeekChat.vue', import.meta.url), 'utf8')
  assert.match(chat, /v-if="message\.sources\?\.length"/)
  assert.match(chat, /\{\{ source\.title \}\}/)
  assert.match(chat, /\{\{ source\.herb_name \}\}/)
  assert.doesNotMatch(chat, /v-html="source\./)
  assert.match(chat, /error\.response\?\.status === 503/)
  const html = renderChatMarkdown('<script>alert(1)</script>')
  assert.doesNotMatch(html, /<script>/)
})

test('chat panel dimensions and scroll container remain in the existing layout', () => {
  const css = readFileSync(new URL('../src/styles/recognition.css', import.meta.url), 'utf8')
  assert.match(css, /\.chat-panel\s*\{[^}]*height: 66\.67dvh;[^}]*max-height: calc\(100dvh - 140px\)/s)
  assert.match(css, /\.chat-messages\s*\{[^}]*overflow-y: auto;/s)
  const chat = readFileSync(new URL('../src/components/recognition/DeepSeekChat.vue', import.meta.url), 'utf8')
  assert.match(chat, /messageArea\.value\.scrollTop = messageArea\.value\.scrollHeight/)
})
