import axios, { type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiErrorResponse } from './types'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''

export const http = axios.create({
  baseURL: baseURL || '/api/v1',
  timeout: 120_000,
  headers: {
    Accept: 'application/json',
  },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    const apiError = error.response?.data?.error
    const message = apiError?.message ?? error.message ?? '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  },
)
