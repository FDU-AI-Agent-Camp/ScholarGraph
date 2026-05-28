import { describe, expect, it } from 'vitest'

import type { FailedDuringStage, PaperStatusData } from '@/api/types'
import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import hss002StatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-002.json'
import processingStatusEnvelope from '../../../docs/api/fixtures/paper-status-processing.json'
import { failedStatus, processingStatus } from '@/test/fixtures/paperStatus'

const FAILED_DURING_VALUES: FailedDuringStage[] = [
  'ingesting',
  'classifying',
  'extracting',
  'storing',
]

function assertPaperStatusDataShape(data: unknown): asserts data is PaperStatusData {
  const body = data as PaperStatusData
  expect(body).toMatchObject({
    paper_id: expect.any(String),
    status: expect.stringMatching(/^(pending|processing|ready|failed)$/),
    percent: expect.any(Number),
    message: expect.any(String),
    updated_at: expect.any(String),
  })
  if (body.failed_during != null) {
    expect(FAILED_DURING_VALUES).toContain(body.failed_during)
  }
}

describe('API contract fixtures vs types.ts', () => {
  it('failed status fixture matches PaperStatusData failed fields', () => {
    assertPaperStatusDataShape(failedStatusEnvelope.data)
    const data = failedStatusEnvelope.data as PaperStatusData
    expect(data.status).toBe('failed')
    expect(data.error_code).toBe('LLM_JSON_INVALID')
    expect(data.failed_during).toBe('classifying')
    expect(data.stage).toBe('failed')
  })

  it('processing status fixture matches PaperStatusData', () => {
    assertPaperStatusDataShape(processingStatusEnvelope.data)
    expect(processingStatusEnvelope.data.status).toBe('processing')
  })

  it('hss-002 per-paper status fixture matches PaperStatusData', () => {
    assertPaperStatusDataShape(hss002StatusEnvelope.data)
    expect(hss002StatusEnvelope.data.paper_id).toBe('hss-002')
    expect(hss002StatusEnvelope.data.status).toBe('processing')
  })

  it('test helpers import the same canonical docs fixtures', () => {
    expect(failedStatus).toEqual(failedStatusEnvelope.data)
    expect(processingStatus.paper_id).toBe(processingStatusEnvelope.data.paper_id)
    expect(processingStatus.status).toBe(processingStatusEnvelope.data.status)
  })

  it('failed fixture omits error fields on non-failed statuses', () => {
    const processing = processingStatusEnvelope.data as PaperStatusData
    expect(processing.error_code).toBeUndefined()
    expect(processing.failed_during).toBeUndefined()
  })
})
