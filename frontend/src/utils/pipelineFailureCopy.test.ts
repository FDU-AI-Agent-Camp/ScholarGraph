import { describe, expect, it } from 'vitest'

import {
  PROCESS_ORPHANED_CODE,
  PROCESS_ORPHANED_TITLE,
  PROCESS_TIMEOUT_CODE,
  PROCESS_TIMEOUT_TITLE,
  QUEUE_TIMEOUT_CODE,
  QUEUE_TIMEOUT_TITLE,
  resolvePipelineFailureTitle,
} from '@/utils/pipelineFailureCopy'

describe('pipelineFailureCopy', () => {
  it('maps PROCESS_ORPHANED / PROCESS_TIMEOUT / QUEUE_TIMEOUT to Chinese titles', () => {
    expect(resolvePipelineFailureTitle(PROCESS_ORPHANED_CODE)).toBe(PROCESS_ORPHANED_TITLE)
    expect(resolvePipelineFailureTitle(PROCESS_TIMEOUT_CODE)).toBe(PROCESS_TIMEOUT_TITLE)
    expect(resolvePipelineFailureTitle(QUEUE_TIMEOUT_CODE)).toBe(QUEUE_TIMEOUT_TITLE)
  })

  it('keeps unknown codes and defaults when absent', () => {
    expect(resolvePipelineFailureTitle('LLM_JSON_INVALID')).toBe('LLM_JSON_INVALID')
    expect(resolvePipelineFailureTitle(null)).toBe('PIPELINE_FAILED')
    expect(resolvePipelineFailureTitle(undefined)).toBe('PIPELINE_FAILED')
  })
})
