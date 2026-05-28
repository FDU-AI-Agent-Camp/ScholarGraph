import { describe, expect, it, vi } from 'vitest'

import { streamPaperQa } from '@/api/qaStream'

const fetchEventSource = vi.fn()

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: (...args: unknown[]) => fetchEventSource(...args),
}))

vi.mock('./client', () => ({
  getApiV1Root: () => '/api/v1',
}))

describe('streamPaperQa integration', () => {
  it('dispatches typed handlers for SSE frames', async () => {
    fetchEventSource.mockImplementation(
      async (
        _url: string,
        options: {
          onmessage?: (ev: { event?: string; data: string }) => void
        },
      ) => {
        options.onmessage?.({
          event: 'message',
          data: JSON.stringify({ delta: '片段' }),
        })
        options.onmessage?.({
          event: 'citation',
          data: JSON.stringify({ paper_id: 'hss-001', node_id: 'n1', label: '论点' }),
        })
        options.onmessage?.({
          event: 'done',
          data: JSON.stringify({ answer_id: 'ans-1', answer: '完整答案' }),
        })
      },
    )

    const deltas: string[] = []
    let citationLabel = ''
    let doneAnswer = ''

    await streamPaperQa('hss-001', '问题？', {
      onMessage: (data) => {
        deltas.push(data.delta)
      },
      onCitation: (data) => {
        citationLabel = data.label
      },
      onDone: (data) => {
        doneAnswer = data.answer ?? ''
      },
    })

    expect(fetchEventSource).toHaveBeenCalledWith(
      '/api/v1/papers/hss-001/qa/stream',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ question: '问题？' }),
      }),
    )
    expect(deltas).toEqual(['片段'])
    expect(citationLabel).toBe('论点')
    expect(doneAnswer).toBe('完整答案')
  })

  it('routes error events to onError', async () => {
    fetchEventSource.mockImplementation(
      async (
        _url: string,
        options: {
          onmessage?: (ev: { event?: string; data: string }) => void
        },
      ) => {
        options.onmessage?.({
          event: 'error',
          data: JSON.stringify({ code: 'QA_FAILED', message: '图谱未就绪' }),
        })
      },
    )

    let errorMessage = ''
    await streamPaperQa('hss-001', 'q', {
      onError: (message) => {
        errorMessage = message
      },
    })

    expect(errorMessage).toBe('图谱未就绪')
  })
})
