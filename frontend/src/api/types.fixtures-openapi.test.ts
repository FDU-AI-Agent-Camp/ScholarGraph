import { describe, expect, it } from 'vitest'

import type {
  DataResponse,
  PaginatedPapers,
  PaperCreateResult,
  PaperDetail,
  PaperStatusData,
  PatrolReport,
  UnifiedPaperGraph,
} from '@/api/types'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import paperCreateFixture from '../../../docs/api/fixtures/paper-create.json'
import paperDetailFixture from '../../../docs/api/fixtures/paper-detail-ready.json'
import patrolFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'
import papersListFixture from '../../../docs/api/fixtures/papers-list.json'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'

describe('docs/api fixtures vs generated-backed types.ts', () => {
  it('assigns failed status fixture to PaperStatusData', () => {
    const body = failedStatusFixture.data as PaperStatusData
    expect(body.error_code).toBe('LLM_JSON_INVALID')
    expect(body.failed_during).toBe('classifying')
  })

  it('assigns patrol fixture data to PatrolReport', () => {
    const report = patrolFixture.data as PatrolReport
    expect(report.mode).toBe('lens_clash')
    expect(report.paper_ids).toEqual(['hss-001', 'hss-002'])
    expect(report.generated_at).toBe('2026-05-19T11:00:00Z')
    expect(report.insights[0]?.insight_id).toBe('ins-001')
    expect(report.insights[0]?.node_refs).toHaveLength(2)
    expect(report.insights[0]?.node_refs[0]?.paper_id).toBe('hss-001')
    expect(report.insights[0]?.node_refs[0]?.node_id).toBe('n_lens_a')
  })

  it('assigns graph fixture data to UnifiedPaperGraph', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    expect(graph.paper_id).toBe('hss-001')
    expect(graph.nodes.length).toBeGreaterThan(0)
    expect(graph.edges[0]?.type).toBe('SUB_ARGUMENT_OF')
  })

  it('assigns paper create fixture to PaperCreateResult inside DataResponse', () => {
    const envelope = paperCreateFixture as DataResponse<PaperCreateResult>
    expect(envelope.data.status).toBe('pending')
    expect(envelope.meta.request_id).toBeTruthy()
  })

  it('assigns papers list fixture items to PaperSummary[]', () => {
    const page = papersListFixture.data as PaginatedPapers
    expect(page.items.length).toBeGreaterThanOrEqual(1)
    expect(page.items[0]?.paper_id).toBeTruthy()
  })

  it('assigns paper detail fixture to PaperDetail', () => {
    const detail = paperDetailFixture.data as PaperDetail
    expect(detail.paper_id).toBe('hss-001')
    expect(detail.classification?.paradigm).toBe('HSS')
  })
})
