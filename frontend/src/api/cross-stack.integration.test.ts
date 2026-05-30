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
})

describe('cross-stack merge (fixture parity for BE HTTP tests)', () => {
  it('failed fixture fields match PaperStatusPanel + openapi FailedDuringStage', () => {
    const data = failedStatusFixture.data as PaperStatusData
    expect(data.status).toBe('failed')
    expect(data.error_code).toBe('LLM_JSON_INVALID')
    expect(data.failed_during).toBe('classifying')
    expect(['ingesting', 'classifying', 'extracting', 'storing']).toContain(data.failed_during)
  })

  it('processing per-paper fixture aligns with hss-002 backend seed path', () => {
    expect(processingStatusFixture.data.paper_id).toBe('hss-002')
    expect(processingStatusFixture.data.percent).toBe(50)
    expect(processingStatusFixture.data.stage).toBe('classifying')
  })
})
