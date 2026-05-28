/**
 * Public API types for the frontend.
 *
 * Domain types are thin aliases over `openapi-typescript` output
 * (`npm run generate:api-types` ← `docs/api/openapi.yaml`).
 * SSE stream event shapes remain hand-written (api-contract §8).
 */

import type { components } from './generated/schema'

type Schema = components['schemas']

/** OpenAPI components — re-export for advanced use (paths, operations). */
export type { components, paths, operations } from './generated/schema'

export type Paradigm = Schema['Paradigm']
export type PaperStatus = Schema['PaperStatus']
export type PipelineStage = Schema['PipelineStage']
export type FailedDuringStage = Schema['FailedDuringStage']

export type Meta = {
  request_id: string
}

export interface DataResponse<T> {
  data: T
  meta: Meta
}

export type ApiErrorBody = Schema['ErrorBody']
export type ApiErrorResponse = Schema['ErrorResponse']

export type ParadigmClassification = Schema['ParadigmClassification']
export type PaperSummary = Schema['PaperSummary']

export interface PaginatedPapers {
  items: PaperSummary[]
  total: number
  offset: number
  limit: number
}

export type PaperDetail = Schema['PaperDetail'] & {
  classification?: ParadigmClassification | null
}

export type PaperCreateResult = {
  paper_id: string
  status: PaperStatus
  message: string
}

export type PaperStatusData = Schema['PaperStatusData']

export type GraphNode = Schema['GraphNode']
export type GraphEdge = Schema['GraphEdge']

export type UnifiedPaperGraph = {
  paper_id: string
  paradigm: Paradigm
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type PatrolInsight = Schema['PatrolInsight'] & {
  /** Optional display field (fixture/UI); not in OpenAPI PatrolInsight yet. */
  severity?: string
}

/** `POST /patrol` response `data` (OpenAPI `PatrolResponse`). */
export type PatrolReport = NonNullable<Schema['PatrolResponse']['data']> & {
  insights: PatrolInsight[]
  /** Legacy UI field when present in fixtures. */
  title?: string
  report_id?: string
}

/** SSE `event: message` payload (api-contract §8). */
export interface QaStreamMessageData {
  delta: string
}

/** SSE `event: citation` payload. */
export interface QaStreamCitationData {
  paper_id: string
  node_id: string
  label: string
}

/** SSE `event: done` payload. */
export interface QaStreamDoneData {
  answer_id: string
  answer?: string
}

/** SSE `event: error` payload. */
export interface QaStreamErrorData {
  code?: string
  message: string
}

export type QaStreamServerEvent =
  | { type: 'message'; data: QaStreamMessageData }
  | { type: 'citation'; data: QaStreamCitationData }
  | { type: 'done'; data: QaStreamDoneData }
  | { type: 'error'; data: QaStreamErrorData }
