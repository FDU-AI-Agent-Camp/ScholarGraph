import { fetchEventSource } from '@microsoft/fetch-event-source'

import { getApiV1Root } from './client'
import type {
  QaStreamCitationData,
  QaStreamDoneData,
  QaStreamErrorData,
  QaStreamMessageData,
  QaStreamServerEvent,
} from './types'

export type {
  QaStreamCitationData,
  QaStreamDoneData,
  QaStreamErrorData,
  QaStreamMessageData,
  QaStreamServerEvent,
}

export interface QaStreamHandlers {
  onMessage?: (data: QaStreamMessageData) => void
  onCitation?: (data: QaStreamCitationData) => void
  onDone?: (data: QaStreamDoneData) => void
  onError?: (message: string) => void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
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
    case 'citation':
      return {
        type: 'citation',
        data: {
          paper_id: String(payload.paper_id ?? ''),
          node_id: String(payload.node_id ?? ''),
          label: String(payload.label ?? ''),
        },
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
