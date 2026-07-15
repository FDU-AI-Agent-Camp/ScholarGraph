import type { FailedDuringStage, PaperStatus, PaperStatusData } from '@/api/types'

export type { FailedDuringStage }

export type TerminalPaperStatus = Extract<PaperStatus, 'ready' | 'ready_with_warnings' | 'failed'>

/** Graph + QA full-capability success set (OpenAPI dual terminal). */
export type GraphInteractivePaperStatus = Extract<PaperStatus, 'ready' | 'ready_with_warnings'>

export interface FailedPaperStatusData extends PaperStatusData {
  status: 'failed'
  error_code?: string
  failed_during?: FailedDuringStage | null
}

const TERMINAL_STATUSES: ReadonlySet<TerminalPaperStatus> = new Set(['ready', 'ready_with_warnings', 'failed'])

const GRAPH_INTERACTIVE_STATUSES: ReadonlySet<GraphInteractivePaperStatus> = new Set(['ready', 'ready_with_warnings'])

export function isTerminalStatus(status: PaperStatus): status is TerminalPaperStatus {
  return TERMINAL_STATUSES.has(status as TerminalPaperStatus)
}

export function isFailedStatus(data: PaperStatusData): data is FailedPaperStatusData {
  return data.status === 'failed'
}

/** Strict clean ready — Badge / no-warning presentation only. */
export function isReadyStatus(data: PaperStatusData): data is PaperStatusData & { status: 'ready' } {
  return data.status === 'ready'
}

/** Full graph canvas / list「图谱」entry — ready ∪ ready_with_warnings. */
export function isGraphInteractiveStatus(status: PaperStatus): status is GraphInteractivePaperStatus {
  return GRAPH_INTERACTIVE_STATUSES.has(status as GraphInteractivePaperStatus)
}

/** QA ask + SSE — same success set as graph interactive. */
export function isQaReadyStatus(status: PaperStatus): status is GraphInteractivePaperStatus {
  return isGraphInteractiveStatus(status)
}

/** In-flight pipeline work that must not be casually interrupted. */
export type ActivePipelinePaperStatus = Extract<PaperStatus, 'processing' | 'indexing'>

const ACTIVE_PIPELINE_STATUSES: ReadonlySet<ActivePipelinePaperStatus> = new Set(['processing', 'indexing'])

export function isActivePipelineStatus(status: PaperStatus): status is ActivePipelinePaperStatus {
  return ACTIVE_PIPELINE_STATUSES.has(status as ActivePipelinePaperStatus)
}

/**
 * Thin MVP preview — only when not yet fully interactive and backend set preview_available.
 * RWW must not degrade into preview.
 */
export function isPreviewAvailableStatus(status: PaperStatus, previewAvailable: boolean): boolean {
  return !isGraphInteractiveStatus(status) && previewAvailable
}
