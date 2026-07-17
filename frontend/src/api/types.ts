/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

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
export type PatrolPoint = Schema['PatrolPoint']

export type PatrolInsight = Schema['PatrolInsight']
export type PatrolExclusionLogic = Schema['PatrolExclusionLogic']
export type PatrolExclusionReason = Schema['PatrolExclusionReason']

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

/** SSE `event: warning` — retrieval degrade (timeout / store down / index not ready). */
export type QaStreamWarningData = {
  code?: string
  message: string
  source?: string
}

export type QaStreamServerEvent =
  | { type: 'message'; data: QaStreamMessageData }
  | { type: 'citation'; data: QaStreamCitationData }
  | { type: 'done'; data: QaStreamDoneData }
  | { type: 'error'; data: QaStreamErrorData }
  | { type: 'warning'; data: QaStreamWarningData }

export type RerankerStatus = 'READY' | 'DISABLED_FALLBACK_ACTIVE' | 'MISCONFIGURED' | 'MOCK_LOCAL'

export type PatrolServiceHealth = {
  status: 'fully_functional' | 'degraded'
  claim_rq_funnel_enabled: boolean
  reranker_status: RerankerStatus
  active_profile: 'ci' | 'demo' | 'prod' | null
  warnings?: string[]
}

export type HealthData = {
  status: 'healthy' | 'degraded'
  version: string
  app_profile?: 'ci' | 'demo' | 'prod' | null
  components: {
    patrol_service: PatrolServiceHealth
  }
  llm_mode: 'mock' | 'live'
  llm_connected: boolean
  llm_note: string
  grobid_url?: string
  grobid_connected?: boolean
  grobid_note?: string
  patrol_claim_rq_funnel_enabled?: boolean
  patrol_config_warnings?: string[]
  patrol_note?: string
}
