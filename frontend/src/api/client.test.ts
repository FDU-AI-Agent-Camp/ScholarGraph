import type { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'

import { ApiClientError, isApiClientError } from '@/api/client'
import type { ApiErrorResponse } from '@/api/types'

describe('ApiClientError', () => {
  it('maps backend error envelope from axios response', () => {
    const axiosError = {
      response: {
        status: 400,
        data: {
          error: {
            code: 'INGEST_FAILED',
            message: '无法解析 PDF',
            details: { filename: 'x.pdf' },
          },
        },
      },
      message: 'Request failed with status code 400',
    } as unknown as AxiosError<ApiErrorResponse>

    const err = ApiClientError.fromAxios(axiosError)
    expect(err.code).toBe('INGEST_FAILED')
    expect(err.message).toBe('无法解析 PDF')
    expect(err.statusCode).toBe(400)
    expect(err.details).toEqual({ filename: 'x.pdf' })
    expect(isApiClientError(err)).toBe(true)
  })

  it('falls back to NETWORK_ERROR when envelope is missing', () => {
    const axiosError = {
      response: undefined,
      message: 'Network Error',
    } as unknown as AxiosError<ApiErrorResponse>

    const err = ApiClientError.fromAxios(axiosError)
    expect(err.code).toBe('NETWORK_ERROR')
    expect(err.statusCode).toBe(0)
  })
})
