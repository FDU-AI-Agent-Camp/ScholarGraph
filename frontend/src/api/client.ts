/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import axios, { type AxiosError, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiErrorBody, ApiErrorResponse, DataResponse } from './types'

export interface ScholarGraphAxiosRequestConfig extends AxiosRequestConfig {
  /** When true, skip the global ElMessage toast; caller handles UX inline. */
  suppressErrorToast?: boolean
}

const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''

const http = axios.create({
  baseURL: baseURL || '/api/v1',
  timeout: 120_000,
  headers: {
    Accept: 'application/json',
  },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    const clientError = ApiClientError.fromAxios(error)
    const config = error.config as ScholarGraphAxiosRequestConfig | undefined
    if (!config?.suppressErrorToast) {
      ElMessage.error(clientError.message)
    }
    return Promise.reject(clientError)
  },
)

/** Typed API failure mapped from the backend error envelope. */
export class ApiClientError extends Error {
  readonly code: string
  readonly statusCode: number
  readonly details?: Record<string, unknown>

  constructor(body: ApiErrorBody, statusCode: number) {
    super(body.message)
    this.name = 'ApiClientError'
    this.code = body.code
    this.statusCode = statusCode
    this.details = body.details
  }

  static fromAxios(error: AxiosError<ApiErrorResponse>): ApiClientError {
    const statusCode = error.response?.status ?? 0
    const body = error.response?.data?.error
    if (body) {
      return new ApiClientError(body, statusCode)
    }
    return new ApiClientError({ code: 'NETWORK_ERROR', message: error.message || '请求失败' }, statusCode)
  }
}

export function isApiClientError(error: unknown): error is ApiClientError {
  return error instanceof ApiClientError
}

/** Resolved `/api/v1` root for JSON and SSE clients. */
export function getApiV1Root(): string {
  const configured = import.meta.env.VITE_API_BASE_URL ?? ''
  return configured ? `${configured.replace(/\/$/, '')}/api/v1` : '/api/v1'
}

export async function getData<T>(url: string, config?: AxiosRequestConfig): Promise<DataResponse<T>> {
  const { data } = await http.get<DataResponse<T>>(url, config)
  return data
}

export async function postData<T>(
  url: string,
  body?: unknown,
  config?: ScholarGraphAxiosRequestConfig,
): Promise<DataResponse<T>> {
  const { data } = await http.post<DataResponse<T>>(url, body, config)
  return data
}

export async function deleteData(url: string, config?: ScholarGraphAxiosRequestConfig): Promise<void> {
  await http.delete(url, config)
}
