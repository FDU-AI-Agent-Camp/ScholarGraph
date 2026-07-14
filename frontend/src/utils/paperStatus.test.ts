import { describe, expect, it } from 'vitest'

import type { PaperStatusData } from '@/api/types'
import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import { failedStatus, processingStatus, readyStatus } from '@/test/fixtures/paperStatus'
import { isFailedStatus, isReadyStatus, isTerminalStatus } from '@/utils/paperStatus'

describe('paperStatus helpers', () => {
  it('isTerminalStatus stops polling for ready / ready_with_warnings / failed', () => {
    expect(isTerminalStatus('ready')).toBe(true)
    expect(isTerminalStatus('ready_with_warnings')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('pending')).toBe(false)
    expect(isTerminalStatus('processing')).toBe(false)
    expect(isTerminalStatus('indexing')).toBe(false)
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

  it('isFailedStatus works on canonical docs/api failed fixture', () => {
    const fixture = failedStatusEnvelope.data as PaperStatusData
    expect(isFailedStatus(fixture)).toBe(true)
    if (isFailedStatus(fixture)) {
      expect(fixture.error_code).toBe('LLM_JSON_INVALID')
    }
  })
})
