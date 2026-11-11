import axios from 'axios'

export const http = axios.create({ baseURL: '/api' })

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      error.message = detail
    } else if (!error.response) {
      error.message = '网络连接失败，请稍后重试'
    }
    return Promise.reject(error)
  },
)
