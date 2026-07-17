/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DataResponse, PaperStatusData } from '@/api/types'
import { statusResponse, failedStatus } from '@/test/fixtures/paperStatus'

const mockGetData = vi.fn()
const mockPostData = vi.fn()
const mockDeleteData = vi.fn()

vi.mock('./client', () => ({
  getData: (...args: unknown[]) => mockGetData(...args),
  postData: (...args: unknown[]) => mockPostData(...args),
  deleteData: (...args: unknown[]) => mockDeleteData(...args),
}))

import {
  deletePaper,
  forceReextractPaper,
  getPaper,
  getPaperGraph,
  getPaperStatus,
  listPapers,
  uploadPaper,
} from '@/api/papers'

describe('papers API module', () => {
  beforeEach(() => {
    mockGetData.mockReset()
    mockPostData.mockReset()
    mockDeleteData.mockReset()
  })

  it('listPapers returns DataResponse from getData', async () => {
    const envelope: DataResponse<{ items: []; total: number; offset: number; limit: number }> = {
      data: { items: [], total: 0, offset: 0, limit: 20 },
      meta: { request_id: 'req-list' },
    }
    mockGetData.mockResolvedValue(envelope)

    const result = await listPapers({ status: 'ready', limit: 20 })

    expect(mockGetData).toHaveBeenCalledWith('/papers', { params: { status: 'ready', limit: 20 } })
    expect(result).toEqual(envelope)
    expect(result.data.total).toBe(0)
  })

  it('getPaperStatus returns typed status envelope', async () => {
    const envelope = statusResponse(failedStatus)
    mockGetData.mockResolvedValue(envelope)

    const result: DataResponse<PaperStatusData> = await getPaperStatus('hss-failed-001')

    expect(mockGetData).toHaveBeenCalledWith('/papers/hss-failed-001/status')
    expect(result.data.error_code).toBe('LLM_JSON_INVALID')
    expect(result.data.failed_during).toBe('classifying')
  })

  it('getPaper and getPaperGraph call expected paths', async () => {
    mockGetData.mockResolvedValue({
      data: { paper_id: 'hss-001', status: 'ready', created_at: '2026-05-19T10:00:00Z' },
      meta: { request_id: 'req-detail' },
    })

    await getPaper('hss-001')
    expect(mockGetData).toHaveBeenCalledWith('/papers/hss-001')

    mockGetData.mockResolvedValue({
      data: { paper_id: 'hss-001', paradigm: 'HSS', nodes: [], edges: [] },
      meta: { request_id: 'req-graph' },
    })
    await getPaperGraph('hss-001')
    expect(mockGetData).toHaveBeenCalledWith('/papers/hss-001/graph')
  })

  it('uploadPaper posts multipart via postData', async () => {
    const file = new File(['%PDF'], 'sample.pdf', { type: 'application/pdf' })
    const envelope = {
      data: { paper_id: 'new-id', status: 'pending' as const, message: '任务已创建' },
      meta: { request_id: 'req-upload' },
    }
    mockPostData.mockResolvedValue(envelope)

    const result = await uploadPaper(file)

    expect(mockPostData).toHaveBeenCalledTimes(1)
    const [url, body, config] = mockPostData.mock.calls[0] as [string, FormData, { headers: Record<string, string> }]
    expect(url).toBe('/papers')
    expect(body).toBeInstanceOf(FormData)
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
    expect(result.data.paper_id).toBe('new-id')
  })

  it('forceReextractPaper posts force query and suppresses toast', async () => {
    const envelope = statusResponse({
      ...failedStatus,
      status: 'pending' as const,
      percent: 0,
      stage: null,
      message: '已强制重新抽取，等待流水线启动…',
      error_code: undefined,
      failed_during: undefined,
    })
    mockPostData.mockResolvedValue(envelope)

    const result = await forceReextractPaper('paper-stuck', { force: true })

    expect(mockPostData).toHaveBeenCalledWith('/papers/paper-stuck/reextract', undefined, {
      params: { force: true },
      suppressErrorToast: true,
    })
    expect(result.data.status).toBe('pending')
  })

  it('deletePaper calls DELETE with optional force and suppresses toast', async () => {
    mockDeleteData.mockResolvedValue(undefined)

    await deletePaper('paper-gone', { force: true })

    expect(mockDeleteData).toHaveBeenCalledWith('/papers/paper-gone', {
      params: { force: true },
      suppressErrorToast: true,
    })
  })
})
