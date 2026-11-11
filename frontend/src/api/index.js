import { http } from './http.js'

export const getHealth = () => http.get('/health')

export function predictImage(file) {
  const form = new FormData()
  form.append('file', file)
  return http.post('/predict', form)
}

export const getHerbs = (q) => http.get('/herbs', { params: { q } })
export const getHerb = (id, config) => http.get(`/herbs/${encodeURIComponent(id)}`, config)

export const getHistory = (page = 1, pageSize = 10, config) =>
  http.get('/history', { ...config, params: { page, page_size: pageSize } })
export const getHistoryRecord = (id, config) => http.get(`/history/${encodeURIComponent(id)}`, config)
export const getHistoryImageUrl = (id) =>
  http.getUri({ url: `/history/${encodeURIComponent(id)}/image` })
export const deleteHistoryRecord = (id) => http.delete(`/history/${encodeURIComponent(id)}`)

export const askHerbalAdvisor = (message, herbId = null, mode = null) =>
  http.post('/ai/chat', {
    message,
    ...(herbId ? { herb_id: herbId } : {}),
    ...(mode ? { mode } : {}),
  })

export function normalizeAdvisorResponse(response) {
  const data = response.data.data
  return {
    answer: data.answer,
    groundingStatus: data.grounding_status,
    answerOrigin: data.answer_origin,
    switchRecommended: data.switch_recommended === true,
    sources: data.grounding_status === 'grounded' && Array.isArray(data.sources)
      ? data.sources.filter((source) => source?.source_type === 'built_in'
        && source.title === '灵枝本草内置药材资料')
      : [],
  }
}

export const getModelInfo = () => http.get('/model/info')
export const getModelMetrics = () => http.get('/model/metrics')
export const getModelChartUrl = (name) =>
  http.getUri({ url: `/model/charts/${encodeURIComponent(name)}` })
