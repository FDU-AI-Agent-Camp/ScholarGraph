import { describe, expect, it } from 'vitest'

import {
  failedStatus,
  processingStatus,
  readyStatus,
} from '@/test/fixtures/paperStatus'
import {
  isFailedStatus,
  isReadyStatus,
  isTerminalStatus,
} from '@/utils/paperStatus'

describe('paperStatus helpers', () => {
  it('isTerminalStatus is true for ready and failed only', () => {
    expect(isTerminalStatus('ready')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('pending')).toBe(false)
    expect(isTerminalStatus('processing')).toBe(false)
  })

  it('isFailedStatus narrows failed payloads with error fields', () => {
    expect(isFailedStatus(processingStatus)).toBe(false)
    expect(isFailedStatus(readyStatus)).toBe(false)
    expect(isFailedStatus(failedStatus)).toBe(true)
    if (isFailedStatus(failedStatus)) {
      expect(failedStatus.error_code).toBe('LLM_JSON_INVALID')
      expect(failedStatus.failed_during).toBe('classifying')
    }
  })

  it('isReadyStatus narrows ready payloads', () => {
    expect(isReadyStatus(readyStatus)).toBe(true)
    expect(isReadyStatus(failedStatus)).toBe(false)
  })
})
