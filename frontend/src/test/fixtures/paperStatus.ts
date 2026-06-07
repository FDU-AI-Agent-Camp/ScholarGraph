import type { DataResponse, PaperStatusData } from '@/api/types'

import failedStatusEnvelope from '../../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import processingStatusEnvelope from '../../../../docs/api/fixtures/paper-status-processing.json'

export const TEST_REQUEST_ID = '550e8400-e29b-41d4-a716-446655440000'

export function statusResponse(body: PaperStatusData): DataResponse<PaperStatusData> {
  return { data: body, meta: { request_id: TEST_REQUEST_ID } }
}

/** Canonical Mock fixture (docs/api/fixtures). */
export const failedStatus = failedStatusEnvelope.data as PaperStatusData

export const processingStatus = processingStatusEnvelope.data as PaperStatusData

export const readyStatus: PaperStatusData = {
  paper_id: 'paper-001',
  status: 'ready',
  percent: 100,
  stage: 'ready',
  message: '处理完成',
  updated_at: '2026-05-19T10:05:00Z',
  extract_warnings: [],
}

export const readyStatusWithExtractFallback: PaperStatusData = {
  ...readyStatus,
  extract_warnings: ['extract_heuristic_fallback'],
}

export const failedStatusWithoutCode: PaperStatusData = {
  paper_id: 'paper-002',
  status: 'failed',
  percent: 0,
  stage: 'failed',
  message: '流水线异常终止',
  updated_at: '2026-05-19T10:03:00Z',
}
