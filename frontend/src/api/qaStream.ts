import { fetchEventSource } from '@microsoft/fetch-event-source'

import { getApiV1Root } from './client'
import type {
  QaStreamCitationData,
  QaStreamDoneData,
  QaStreamErrorData,
  QaStreamMessageData,
  QaStreamServerEvent,
  QaStreamWarningData,
} from './types'
import type { ChunkPreviewState } from '@/utils/qaCitations'

export type {
  QaStreamCitationData,
  QaStreamDoneData,
  QaStreamErrorData,
  QaStreamMessageData,
  QaStreamServerEvent,
  QaStreamWarningData,
}

export interface QaStreamHandlers {
  onMessage?: (data: QaStreamMessageData) => void
  onCitation?: (data: QaStreamCitationData) => void
  onDone?: (data: QaStreamDoneData) => void
  onError?: (message: string) => void
  onWarning?: (data: QaStreamWarningData) => void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseChunkPreviewState(raw: unknown): ChunkPreviewState {
  const value = String(raw ?? 'ready')
  switch (value) {
    case 'ready':
    case 'indexing':
    case 'retrieval_timeout':
    case 'l2_timeout':
    case 'hallucinated_id':
      return value
    default:
      return 'ready'
  }
}

function parseCitationPayload(payload: Record<string, unknown>): QaStreamCitationData | null {
  const paperId = String(payload.paper_id ?? '')
  const label = String(payload.label ?? '')
  const citationType = payload.type != null ? String(payload.type) : 'node'

  switch (citationType) {
    case 'node':
      return {
        type: 'node',
        paper_id: paperId,
        node_id: String(payload.node_id ?? ''),
        label,
      }
    case 'edge':
      return {
        type: 'edge',
        paper_id: paperId,
        edge_id: String(payload.edge_id ?? ''),
        label,
      }
    case 'chunk':
      return {
        type: 'chunk',
        paper_id: paperId,
        chunk_id: String(payload.chunk_id ?? ''),
        label,
        text_preview: String(payload.text_preview ?? ''),
        preview_state: parseChunkPreviewState(payload.preview_state),
      }
    case 'page': {
      const rawPage = payload.page
      const page = typeof rawPage === 'number' && Number.isFinite(rawPage) ? rawPage : String(rawPage ?? '')
      return {
        type: 'page',
        paper_id: paperId,
        page,
        label,
      }
    }
    default:
      return null
  }
}

/** Parse one SSE frame into a discriminated union (exported for tests). */
export function parseQaStreamEvent(eventName: string, rawData: string): QaStreamServerEvent | null {
  let payload: unknown
  try {
    payload = JSON.parse(rawData) as unknown
  } catch {
    return null
  }
  if (!isRecord(payload)) {
    return null
  }

  switch (eventName) {
    case 'message':
      return { type: 'message', data: { delta: String(payload.delta ?? '') } }
    case 'citation': {
      const citation = parseCitationPayload(payload)
      return citation ? { type: 'citation', data: citation } : null
    }
    case 'done':
      return {
        type: 'done',
        data: {
          answer_id: String(payload.answer_id ?? ''),
          answer: payload.answer != null ? String(payload.answer) : undefined,
        },
      }
    case 'error':
      return {
        type: 'error',
        data: {
          code: payload.code != null ? String(payload.code) : undefined,
          message: String(payload.message ?? 'SSE error'),
        },
      }
    case 'warning':
      return {
        type: 'warning',
        data: {
          code: payload.code != null ? String(payload.code) : undefined,
          message: String(payload.message ?? ''),
          source: payload.source != null ? String(payload.source) : undefined,
        },
      }
    default:
      return null
  }
}

function dispatchQaStreamEvent(event: QaStreamServerEvent, handlers: QaStreamHandlers): void {
  switch (event.type) {
    case 'message':
      handlers.onMessage?.(event.data)
      break
    case 'citation':
      handlers.onCitation?.(event.data)
      break
    case 'done':
      handlers.onDone?.(event.data)
      break
    case 'error':
      handlers.onError?.(event.data.message)
      break
    case 'warning':
      handlers.onWarning?.(event.data)
      break
    default: {
      const _exhaustive: never = event
      return _exhaustive
    }
  }
}

/** POST SSE for multi-scale QA (frozen contract). */
export async function streamPaperQa(
  paperId: string,
  question: string,
  handlers: QaStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await fetchEventSource(`${getApiV1Root()}/papers/${paperId}/qa/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ question }),
    signal,
    onmessage(ev) {
      if (!ev.data) return
      const parsed = parseQaStreamEvent(ev.event || 'message', ev.data)
      if (parsed) {
        dispatchQaStreamEvent(parsed, handlers)
      }
    },
    onerror(err) {
      handlers.onError?.(err instanceof Error ? err.message : '流式连接中断')
      throw err
    },
  })
}
