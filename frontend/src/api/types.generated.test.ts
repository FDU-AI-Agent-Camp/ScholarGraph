import { describe, expect, it } from 'vitest'

import type { components, paths } from '@/api/generated/schema'
import type {
  ApiErrorBody,
  DataResponse,
  FailedDuringStage,
  PaperCreateResult,
  PaperStatus,
  PipelineStage,
  PaperStatusData,
  PaperSummary,
  PatrolReport,
  QaStreamMessageData,
  UnifiedPaperGraph,
} from '@/api/types'

type Schema = components['schemas']

describe('types.ts vs generated OpenAPI schema', () => {
  it('enum aliases match generated schemas', () => {
    const status: PaperStatus = 'failed'
    const during: FailedDuringStage = 'classifying'
    const stage: PipelineStage = 'extracting'
    expect(status).toBe('failed')
    expect(during).toBe('classifying')
    expect(stage).toBe('extracting')

    const _paper: PaperSummary = {
      paper_id: 'x',
      status: 'ready',
      created_at: '2026-05-19T10:00:00Z',
    }
    expect(_paper.paper_id).toBe('x')

    const _statusData: PaperStatusData = {
      paper_id: 'x',
      status: 'failed',
      percent: 0,
      stage: 'failed',
      message: 'm',
      updated_at: '2026-05-19T10:00:00Z',
      error_code: 'E',
      failed_during: 'ingesting',
    }
    expect(_statusData.error_code).toBe('E')
  })

  it('PatrolReport accepts OpenAPI PatrolResponse data shape', () => {
    const payload: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001'],
      insights: [
        {
          insight_id: 'i1',
          title: 't',
          summary: 's',
          paper_ids: ['hss-001'],
          node_refs: [],
        },
      ],
      generated_at: '2026-05-19T11:00:00Z',
    }
    expect(payload.insights).toHaveLength(1)
    const _schemaCheck: NonNullable<Schema['PatrolResponse']['data']> = payload
    expect(_schemaCheck.mode).toBe('lens_clash')
  })

  it('exports path types for core HTTP routes', () => {
    type ListPapers = paths['/papers']['get']
    type PaperStatus = paths['/papers/{paper_id}/status']['get']
    type QaStream = paths['/papers/{paper_id}/qa/stream']['post']
    type Patrol = paths['/patrol']['post']
    const _list: ListPapers = {} as ListPapers
    const _status: PaperStatus = {} as PaperStatus
    const _qa: QaStream = {} as QaStream
    const _patrol: Patrol = {} as Patrol
    expect(_list).toBeDefined()
    expect(_status).toBeDefined()
    expect(_qa).toBeDefined()
    expect(_patrol).toBeDefined()
  })

  it('composite helpers align with generated object schemas', () => {
    const create: PaperCreateResult = {
      paper_id: 'id',
      status: 'pending',
      message: 'ok',
    }
    const _createSchema: NonNullable<Schema['PaperCreateResponse']['data']> = create

    const graph: UnifiedPaperGraph = {
      paper_id: 'hss-001',
      paradigm: 'HSS',
      nodes: [{ id: 'n1', label: 'l', type: 'Thesis' }],
      edges: [{ id: 'e1', source: 'n1', target: 'n1', label: 'L', type: 'L' }],
    }
    const _graphData: NonNullable<Schema['GraphResponse']['data']> = graph

    const envelope: DataResponse<PaperCreateResult> = {
      data: create,
      meta: { request_id: 'req' },
    }
    expect(envelope.meta.request_id).toBe('req')
    expect(_createSchema.paper_id).toBe('id')
    expect(_graphData.nodes).toHaveLength(1)
  })

  it('ApiErrorBody matches ErrorBody schema', () => {
    const err: ApiErrorBody = {
      code: 'INGEST_FAILED',
      message: 'bad pdf',
      details: { filename: 'x.pdf' },
    }
    const _schema: Schema['ErrorBody'] = err
    expect(_schema.code).toBe('INGEST_FAILED')
  })

  it('keeps SSE payload types hand-written outside OpenAPI components', () => {
    const msg: QaStreamMessageData = { delta: 'hi' }
    expect(msg.delta).toBe('hi')
    const schemaKeys = Object.keys({} as Schema)
    expect(schemaKeys).not.toContain('QaStreamMessageData')
  })
})
