import { describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { getUnknownErrorMessage, logUnknownError } from '@/utils/errors'

describe('getUnknownErrorMessage', () => {
  it('reads ApiClientError message', () => {
    const err = new ApiClientError({ code: 'X', message: '业务错误' }, 400)
    expect(getUnknownErrorMessage(err)).toBe('业务错误')
  })

  it('reads Error message', () => {
    expect(getUnknownErrorMessage(new Error('boom'))).toBe('boom')
  })

  it('falls back for non-error values', () => {
    expect(getUnknownErrorMessage(null)).toBe('未知错误')
  })
})

describe('logUnknownError', () => {
  it('logs ApiClientError code and message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    logUnknownError('test', new ApiClientError({ code: 'E1', message: '失败' }, 500))
    expect(spy).toHaveBeenCalledWith('[test]', 'E1', '失败')
    spy.mockRestore()
  })
})
