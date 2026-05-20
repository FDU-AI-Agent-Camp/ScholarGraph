import { fetchEventSource } from '@microsoft/fetch-event-source'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''
const apiRoot = baseURL ? `${baseURL.replace(/\/$/, '')}/api/v1` : '/api/v1'

export interface QaStreamHandlers {
  onMessage?: (delta: string) => void
  onCitation?: (payload: Record<string, unknown>) => void
  onDone?: (payload: Record<string, unknown>) => void
  onError?: (message: string) => void
}

/** POST SSE for multi-scale QA (frozen contract). */
export async function streamPaperQa(
  paperId: string,
  question: string,
  handlers: QaStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await fetchEventSource(`${apiRoot}/papers/${paperId}/qa/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ question }),
    signal,
    onmessage(ev) {
      if (!ev.data) return
      const payload = JSON.parse(ev.data) as Record<string, unknown>
      switch (ev.event) {
        case 'message':
          handlers.onMessage?.(String(payload.delta ?? ''))
          break
        case 'citation':
          handlers.onCitation?.(payload)
          break
        case 'done':
          handlers.onDone?.(payload)
          break
        case 'error':
          handlers.onError?.(String(payload.message ?? 'SSE error'))
          break
        default:
          break
      }
    },
    onerror(err) {
      handlers.onError?.(err instanceof Error ? err.message : '流式连接中断')
      throw err
    },
  })
}
