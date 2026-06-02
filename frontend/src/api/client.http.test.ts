import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DataResponse } from '@/api/types'

const mockGet = vi.hoisted(() => vi.fn())
const mockPost = vi.hoisted(() => vi.fn())
const interceptorErrorHandler = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      interceptors: {
        response: {
          use: vi.fn((_ok: unknown, onRejected: (err: unknown) => unknown) => {
            interceptorErrorHandler.mockImplementation(onRejected)
          }),
        },
      },
    })),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn() },
}))

describe('client HTTP helpers', () => {
  beforeEach(async () => {
    vi.resetModules()
    mockGet.mockReset()
    mockPost.mockReset()
    interceptorErrorHandler.mockReset()
    vi.unstubAllEnvs()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('getData unwraps axios response data envelope', async () => {
    const envelope: DataResponse<{ ok: boolean }> = {
      data: { ok: true },
      meta: { request_id: 'req-1' },
    }
    mockGet.mockResolvedValue({ data: envelope })

    const { getData } = await import('./client')
    const result = await getData<{ ok: boolean }>('/health')

    expect(mockGet).toHaveBeenCalledWith('/health', undefined)
    expect(result).toEqual(envelope)
  })

  it('postData forwards body and config', async () => {
    const envelope: DataResponse<{ id: string }> = {
      data: { id: 'x' },
      meta: { request_id: 'req-2' },
    }
    mockPost.mockResolvedValue({ data: envelope })

    const { postData } = await import('./client')
    const body = { paper_ids: ['a'] }
    const result = await postData<{ id: string }>('/patrol', body, { headers: { 'X-Test': '1' } })

    expect(mockPost).toHaveBeenCalledWith('/patrol', body, { headers: { 'X-Test': '1' } })
    expect(result.data.id).toBe('x')
  })

  it('response interceptor rejects ApiClientError', async () => {
    mockGet.mockImplementation(async () => {
      const axiosError = {
        response: {
          status: 404,
          data: { error: { code: 'PAPER_NOT_FOUND', message: '论文不存在' } },
        },
        message: 'Not Found',
      }
      return interceptorErrorHandler(axiosError)
    })

    const { getData, ApiClientError, isApiClientError } = await import('./client')

    await expect(getData('/papers/missing')).rejects.toBeInstanceOf(ApiClientError)
    await expect(getData('/papers/missing')).rejects.toMatchObject({
      code: 'PAPER_NOT_FOUND',
      statusCode: 404,
    })

    try {
      await getData('/papers/missing')
    } catch (error) {
      expect(isApiClientError(error)).toBe(true)
    }
  })

  it('response interceptor shows ElMessage.error for API failures', async () => {
    const { ElMessage } = await import('element-plus')
    mockGet.mockImplementation(async () => {
      const axiosError = {
        response: {
          status: 500,
          data: { error: { code: 'SERVER', message: '服务不可用' } },
        },
        message: 'Internal Server Error',
      }
      return interceptorErrorHandler(axiosError)
    })

    const { getData } = await import('./client')

    await expect(getData('/papers')).rejects.toMatchObject({ code: 'SERVER' })
    expect(ElMessage.error).toHaveBeenCalledWith('服务不可用')
  })

  it('suppressErrorToast skips global toast for upload client', async () => {
    const { ElMessage } = await import('element-plus')
    vi.mocked(ElMessage.error).mockClear()
    mockGet.mockReset()
    mockPost.mockReset()
    interceptorErrorHandler.mockReset()
    vi.resetModules()

    mockPost.mockImplementation(async (_url, _body, config) => {
      const axiosError = {
        config,
        response: {
          status: 400,
          data: { error: { code: 'INGEST_FAILED', message: '无法解析 PDF' } },
        },
        message: 'Bad Request',
      }
      return interceptorErrorHandler(axiosError)
    })

    const { postData } = await import('./client')

    await expect(postData('/papers', new FormData(), { suppressErrorToast: true })).rejects.toMatchObject({
      code: 'INGEST_FAILED',
    })
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('getApiV1Root respects VITE_API_BASE_URL', async () => {
    const { getApiV1Root } = await import('./client')
    vi.stubEnv('VITE_API_BASE_URL', '')
    expect(getApiV1Root()).toBe('/api/v1')

    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000/')
    expect(getApiV1Root()).toBe('http://127.0.0.1:8000/api/v1')
  })
})
