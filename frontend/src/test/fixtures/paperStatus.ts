import type { DataResponse, PaperStatusData } from '@/api/types'

export const TEST_REQUEST_ID = '550e8400-e29b-41d4-a716-446655440000'

export function statusResponse(body: PaperStatusData): DataResponse<PaperStatusData> {
  return { data: body, meta: { request_id: TEST_REQUEST_ID } }
}

export const processingStatus: PaperStatusData = {
  paper_id: 'paper-001',
  status: 'processing',
  percent: 50,
  stage: 'classifying',
  message: '正在识别范式与理论视角…',
  updated_at: '2026-05-19T10:02:30Z',
}

export const readyStatus: PaperStatusData = {
  paper_id: 'paper-001',
  status: 'ready',
  percent: 100,
  stage: 'ready',
  message: '处理完成',
  updated_at: '2026-05-19T10:05:00Z',
}

export const failedStatus: PaperStatusData = {
  paper_id: 'paper-001',
  status: 'failed',
  percent: 40,
  stage: 'failed',
  message: '分类阶段 LLM 返回无效 JSON',
  updated_at: '2026-05-19T10:03:00Z',
  error_code: 'LLM_JSON_INVALID',
  failed_during: 'classifying',
}

export const failedStatusWithoutCode: PaperStatusData = {
  paper_id: 'paper-002',
  status: 'failed',
  percent: 0,
  stage: 'failed',
  message: '流水线异常终止',
  updated_at: '2026-05-19T10:03:00Z',
}
