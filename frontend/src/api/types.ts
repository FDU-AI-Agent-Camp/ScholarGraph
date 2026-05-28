/**
 * Hand-maintained types aligned with docs/api/openapi.yaml.
 * Key schemas: PaperStatusData, FailedDuringStage, PipelineStage, PaperStatus.
 */

export type Paradigm = 'STEM' | 'HSS'
export type PaperStatus = 'pending' | 'processing' | 'ready' | 'failed'
export type PipelineStage =
  | 'ingesting'
  | 'classifying'
  | 'extracting'
  | 'storing'
  | 'ready'
  | 'failed'

export interface Meta {
  request_id: string
}

export interface ApiErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface ApiErrorResponse {
  error: ApiErrorBody
}

export interface DataResponse<T> {
  data: T
  meta: Meta
}

export interface PaginatedPapers {
  items: PaperSummary[]
  total: number
  offset: number
  limit: number
}

export interface ParadigmClassification {
  paradigm: Paradigm
  confidence: number
  reason: string
}

export interface PaperSummary {
  paper_id: string
  title?: string | null
  paradigm?: Paradigm | null
  status: PaperStatus
  created_at: string
  updated_at?: string | null
}

export interface PaperDetail extends PaperSummary {
  classification?: ParadigmClassification | null
}

/** OpenAPI `FailedDuringStage` — pipeline step when `status=failed`. */
export type FailedDuringStage = Exclude<PipelineStage, 'ready' | 'failed'>

export interface PaperStatusData {
  paper_id: string
  status: PaperStatus
  percent: number
  stage: PipelineStage | null
  message: string
  updated_at: string
  /** OpenAPI optional; required semantically when `status=failed`. */
  error_code?: string
  /** OpenAPI `FailedDuringStage`; pipeline step active at failure. */
  failed_during?: FailedDuringStage | null
}

export interface GraphNode {
  id: string
  label: string
  type: string
  data?: Record<string, unknown>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  type: string
  data?: Record<string, unknown>
}

export interface UnifiedPaperGraph {
  paper_id: string
  paradigm: Paradigm
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface PatrolInsight {
  insight_id: string
  title: string
  summary: string
  severity: string
  paper_ids: string[]
}

export interface PatrolReport {
  report_id: string
  title: string
  insights: PatrolInsight[]
}
