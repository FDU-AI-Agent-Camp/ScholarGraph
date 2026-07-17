/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Cross-stack merge verification: FE API client ↔ docs/api/fixtures ↔ backend contract.
 *
 * Simulates FastAPI `{ data, meta }` envelopes the Vue app consumes after merging
 * feature/frontend + feature/backend/platform + feature/backend/ingest into develop.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as client from '@/api/client'
import * as papersApi from '@/api/papers'
import * as patrolApi from '@/api/patrol'
import type { DataResponse, PaperStatusData, PatrolReport, UnifiedPaperGraph } from '@/api/types'
import { isFailedStatus, isTerminalStatus } from '@/utils/paperStatus'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import processingStatusFixture from '../../../docs/api/fixtures/paper-status-hss-002.json'
import papersListFixture from '../../../docs/api/fixtures/papers-list.json'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import patrolFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'
import paperDetailReadyFixture from '../../../docs/api/fixtures/paper-detail-ready.json'
import classifyFallbackStatusFixture from '../../../docs/api/fixtures/paper-status-classify-fallback.json'
import classifyFallbackDetailFixture from '../../../docs/api/fixtures/paper-detail-classify-fallback.json'
import {
  CLASSIFIER_HEURISTIC_FALLBACK_CODE,
  CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
  resolveClassifyWarningMessages,
} from '@/utils/classifyWarnings'

const failedStatusResponse = failedStatusFixture as DataResponse<PaperStatusData>
const processingStatusResponse = processingStatusFixture as DataResponse<PaperStatusData>

afterEach(() => {
  vi.restoreAllMocks()
})

describe('cross-stack merge (FE papers API ↔ fixture envelopes)', () => {
  it('getPaperStatus calls /papers/{id}/status and parses failed merge fixture', async () => {
    const getDataSpy = vi.spyOn(client, 'getData').mockResolvedValue(failedStatusResponse)

    const result = await papersApi.getPaperStatus('hss-failed-001')

    expect(getDataSpy).toHaveBeenCalledWith('/papers/hss-failed-001/status')
    expect(isFailedStatus(result.data)).toBe(true)
    expect(isTerminalStatus(result.data.status)).toBe(true)
    expect(result.data.error_code).toBe('LLM_JSON_INVALID')
    expect(result.data.failed_during).toBe('classifying')
    expect(result.data.stage).toBe('failed')
    expect(result.data.percent).toBe(40)
    expect(result.meta.request_id).toBeTruthy()
  })

  it('getPaperStatus parses processing fixture without failure fields', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(processingStatusResponse)

    const result = await papersApi.getPaperStatus('hss-002')

    expect(result.data.status).toBe('processing')
    expect(result.data.stage).toBe('classifying')
    expect(result.data.error_code).toBeUndefined()
    expect(result.data.failed_during).toBeUndefined()
    expect(isTerminalStatus(result.data.status)).toBe(false)
  })

  it('listPapers parses papers-list fixture used by both BE seed and FE table', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(papersListFixture)

    const result = await papersApi.listPapers()

    expect(result.data.items.length).toBeGreaterThanOrEqual(1)
    const ids = result.data.items.map((row) => row.paper_id)
    expect(ids).toContain('hss-001')
    expect(ids).toContain('hss-failed-001')
  })

  it('getPaper returns ready detail for graph navigation path', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(paperDetailReadyFixture)

    const result = await papersApi.getPaper('hss-001')

    expect(result.data.paper_id).toBe('hss-001')
    expect(result.data.status).toBe('ready')
    expect(result.data.classify_warnings).toEqual([])
  })

  it('getPaperStatus parses classify-fallback fixture for Phase G polling UX', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(classifyFallbackStatusFixture)

    const result = await papersApi.getPaperStatus('hss-classify-fallback-001')

    expect(result.data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(resolveClassifyWarningMessages(result.data.classify_warnings)).toEqual([
      CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('getPaper parses classify-fallback detail fixture for DetailView alert', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(classifyFallbackDetailFixture)

    const result = await papersApi.getPaper('hss-classify-fallback-001')

    expect(result.data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(result.data.classification?.reason).toBeTruthy()
    expect(result.data.classification?.reason).not.toBe(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
  })

  it('getPaperGraph parses graph-hss fixture shape', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(graphFixture as DataResponse<UnifiedPaperGraph>)

    const result = await papersApi.getPaperGraph('hss-001')

    expect(result.data.paper_id).toBe('hss-001')
    expect(result.data.nodes.length).toBeGreaterThan(0)
    expect(result.data.edges[0]?.type).toBeTruthy()
  })

  it('runPatrol POST /patrol parses patrol-lens-clash fixture', async () => {
    const postSpy = vi.spyOn(client, 'postData').mockResolvedValue(patrolFixture as DataResponse<PatrolReport>)

    const result = await patrolApi.runPatrol(['hss-001', 'hss-002'], { mode: 'lens_clash' })

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['hss-001', 'hss-002'],
      mode: 'lens_clash',
    })
    expect(result.data.mode).toBe('lens_clash')
    expect(result.data.insights[0]?.node_refs.length).toBeGreaterThan(0)
    expect(result.data.insights[0]?.insight_id).toBe('ins-001')
  })

  it('uploadPaper posts multipart with suppressErrorToast for inline upload UX', async () => {
    const postSpy = vi.spyOn(client, 'postData').mockResolvedValue({
      data: { paper_id: 'new-id', status: 'pending', message: '任务已创建' },
      meta: { request_id: 'req-upload' },
    })
    const file = new File(['%PDF'], 'sample.pdf', { type: 'application/pdf' })

    await papersApi.uploadPaper(file)

    expect(postSpy).toHaveBeenCalledTimes(1)
    const [, body, config] = postSpy.mock.calls[0] as [string, FormData, { suppressErrorToast?: boolean }]
    expect(body).toBeInstanceOf(FormData)
    expect(config.suppressErrorToast).toBe(true)
  })

  it('getPaperGraph rejection maps to ApiClientError for 409 GRAPH_NOT_READY', async () => {
    vi.spyOn(client, 'getData').mockRejectedValue(
      new client.ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱尚未就绪，请轮询 status 接口' }, 409),
    )

    await expect(papersApi.getPaperGraph('hss-002')).rejects.toMatchObject({
      code: 'GRAPH_NOT_READY',
      statusCode: 409,
    })
  })

  it('runPatrol rejection maps 409 GRAPH_NOT_READY for patrol red path', async () => {
    vi.spyOn(client, 'postData').mockRejectedValue(
      new client.ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409),
    )

    await expect(patrolApi.runPatrol(['hss-001', 'hss-002'])).rejects.toMatchObject({
      code: 'GRAPH_NOT_READY',
      statusCode: 409,
    })
  })

  it('runPatrol rejection maps 422 PATROL_INSUFFICIENT_DATA', async () => {
    vi.spyOn(client, 'postData').mockRejectedValue(
      new client.ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '巡检数据不足' }, 422),
    )

    await expect(patrolApi.runPatrol(['hss-001', 'hss-002'])).rejects.toMatchObject({
      code: 'PATROL_INSUFFICIENT_DATA',
      statusCode: 422,
    })
  })
})

describe('cross-stack merge (fixture parity for BE HTTP tests)', () => {
  it('failed fixture fields match PaperStatusPanel + openapi FailedDuringStage', () => {
    const data = failedStatusFixture.data as PaperStatusData
    expect(data.status).toBe('failed')
    expect(data.error_code).toBe('LLM_JSON_INVALID')
    expect(data.failed_during).toBe('classifying')
    expect(['ingesting', 'head_refining', 'classifying', 'extracting', 'storing']).toContain(data.failed_during)
  })

  it('processing per-paper fixture aligns with hss-002 backend seed path', () => {
    expect(processingStatusFixture.data.paper_id).toBe('hss-002')
    expect(processingStatusFixture.data.percent).toBe(50)
    expect(processingStatusFixture.data.stage).toBe('classifying')
  })

  it('M2 graph-hss fixture node ids align with BE qa_samples citation targets', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const ids = graph.nodes.map((node) => node.id)
    expect(ids).toContain('n1')
    expect(ids).toContain('n2')
    expect(ids).toContain('n_lens')
    const thesis = graph.nodes.find((node) => node.type === 'Thesis')
    const lens = graph.nodes.find((node) => node.type === 'AnalyticalLens')
    expect(thesis?.id).toBe('n1')
    expect(lens?.id).toBe('n_lens')
  })

  it('classify-fallback fixtures align with BE Phase G OpenAPI examples', () => {
    const status = classifyFallbackStatusFixture.data as PaperStatusData
    const detail = classifyFallbackDetailFixture.data as import('@/api/types').PaperDetail
    expect(status.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(detail.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(resolveClassifyWarningMessages(status.classify_warnings)).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE])
  })
})
