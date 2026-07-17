/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

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
  preview_available: true,
  extract_warnings: [],
  classify_warnings: [],
}

/** G1: quality-gated success terminal — graph/QA available with warnings. */
export const readyWithWarningsStatus: PaperStatusData = {
  paper_id: 'paper-001',
  status: 'ready_with_warnings',
  percent: 100,
  stage: 'ready',
  message: '图谱可用，存在质量或索引警告',
  updated_at: '2026-05-19T10:05:00Z',
  preview_available: true,
  extract_warnings: ['extract_quality_gate_failed'],
  classify_warnings: [],
}

export const indexingStatus: PaperStatusData = {
  paper_id: 'paper-001',
  status: 'indexing',
  percent: 90,
  stage: 'storing',
  message: '正在构建向量索引',
  updated_at: '2026-05-19T10:04:00Z',
  preview_available: false,
  extract_warnings: [],
  classify_warnings: [],
}

export const readyStatusWithExtractFallback: PaperStatusData = {
  ...readyStatus,
  extract_warnings: ['extract_heuristic_fallback'],
}

export const readyStatusWithClassifyFallback: PaperStatusData = {
  ...readyStatus,
  classify_warnings: ['classifier_heuristic_fallback'],
}

export const classifyingStatusWithClassifyFallback: PaperStatusData = {
  ...processingStatus,
  stage: 'classifying',
  percent: 50,
  classify_warnings: ['classifier_heuristic_fallback'],
}

export const readyStatusWithBothFallbacks: PaperStatusData = {
  ...readyStatus,
  extract_warnings: ['extract_heuristic_fallback'],
  classify_warnings: ['classifier_heuristic_fallback'],
}

export const failedStatusWithoutCode: PaperStatusData = {
  paper_id: 'paper-002',
  status: 'failed',
  percent: 0,
  stage: 'failed',
  message: '流水线异常终止',
  updated_at: '2026-05-19T10:03:00Z',
  preview_available: false,
}

/** Processing orphan heal — cold-boot PROCESS_ORPHANED. */
export const failedStatusProcessOrphaned: PaperStatusData = {
  paper_id: 'paper-orphan',
  status: 'failed',
  percent: 0,
  stage: 'failed',
  message: '系统重启导致解析中断，请尝试重新提取。',
  updated_at: '2026-05-19T10:03:00Z',
  preview_available: false,
  error_code: 'PROCESS_ORPHANED',
  failed_during: 'extracting',
}

/** Processing orphan heal — wall-clock PROCESS_TIMEOUT. */
export const failedStatusProcessTimeout: PaperStatusData = {
  paper_id: 'paper-timeout',
  status: 'failed',
  percent: 0,
  stage: 'failed',
  message: '解析超时未推进，任务已标记失败，请尝试重新提取。',
  updated_at: '2026-05-19T10:03:00Z',
  preview_available: false,
  error_code: 'PROCESS_TIMEOUT',
  failed_during: 'extracting',
}

/** Pending queue wall-clock — QUEUE_TIMEOUT. */
export const failedStatusQueueTimeout: PaperStatusData = {
  paper_id: 'paper-queue-timeout',
  status: 'failed',
  percent: 0,
  stage: 'failed',
  message: '排队超时，服务器任务积压过久，请稍后重新上传或强制重新抽取。',
  updated_at: '2026-05-19T10:03:00Z',
  preview_available: false,
  error_code: 'QUEUE_TIMEOUT',
}
