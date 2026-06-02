import type { FailedDuringStage, PaperStatus, PaperStatusData } from '@/api/types'

export type { FailedDuringStage }

export type TerminalPaperStatus = Extract<PaperStatus, 'ready' | 'failed'>

export interface FailedPaperStatusData extends PaperStatusData {
  status: 'failed'
  error_code?: string
  failed_during?: FailedDuringStage | null
}

const TERMINAL_STATUSES: ReadonlySet<TerminalPaperStatus> = new Set(['ready', 'failed'])

export function isTerminalStatus(status: PaperStatus): status is TerminalPaperStatus {
  return TERMINAL_STATUSES.has(status as TerminalPaperStatus)
}

export function isFailedStatus(data: PaperStatusData): data is FailedPaperStatusData {
  return data.status === 'failed'
}

export function isReadyStatus(data: PaperStatusData): data is PaperStatusData & { status: 'ready' } {
  return data.status === 'ready'
}
