/**
 * Public API types for the frontend.
 *
 * Domain types are thin aliases over `openapi-typescript` output
 * (`npm run generate:api-types` ← `docs/api/openapi.yaml`).
 * SSE 载荷见 docs/api/sse-qa.md 与 OpenAPI `QaStream*` schemas。
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

export type PaperDetail = Omit<Schema['PaperDetail'], 'preview_available'> & {
  classification?: ParadigmClassification | null
  preview_available?: boolean
}

export type PaperCreateResult = {
  paper_id: string
  status: PaperStatus
  message: string
}

export type PaperStatusData = Omit<Schema['PaperStatusData'], 'preview_available'> & {
  preview_available?: boolean
}

export type GraphNode = Schema['GraphNode']
export type GraphEdge = Schema['GraphEdge']

export type UnifiedPaperGraph = {
  paper_id: string
  paradigm: Paradigm
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type PatrolMode = Schema['PatrolMode']

export type PatrolInsight = Schema['PatrolInsight']

/** `POST /patrol` response `data` (OpenAPI `PatrolResponse`). */
export type PatrolReport = {
  mode: PatrolMode
  paper_ids: string[]
  insights: PatrolInsight[]
  generated_at: string
}

/** SSE `event: message` payload. */
export type QaStreamMessageData = Schema['QaStreamMessageData']

/** SSE `event: citation` payload (V2 discriminated union). */
export type QaStreamCitationData = Schema['QaStreamCitation']

/** SSE `event: done` payload. */
export type QaStreamDoneData = Schema['QaStreamDoneData']

/** SSE `event: error` payload. */
export type QaStreamErrorData = Schema['QaStreamErrorData']

export type QaStreamServerEvent =
  | { type: 'message'; data: QaStreamMessageData }
  | { type: 'citation'; data: QaStreamCitationData }
  | { type: 'done'; data: QaStreamDoneData }
  | { type: 'error'; data: QaStreamErrorData }
