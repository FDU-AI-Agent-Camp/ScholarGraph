/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

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
          data: JSON.stringify({ type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '论点' }),
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

  it('routes fetchEventSource onerror to onError before rejecting', async () => {
    fetchEventSource.mockImplementation(
      async (
        _url: string,
        options: {
          onerror?: (err: unknown) => void
        },
      ) => {
        options.onerror?.(new Error('connection reset'))
      },
    )

    let errorMessage = ''
    await expect(
      streamPaperQa('hss-001', 'q', {
        onError: (message) => {
          errorMessage = message
        },
      }),
    ).rejects.toThrow('connection reset')

    expect(errorMessage).toBe('connection reset')
  })

  it('sends Accept text/event-stream and POST JSON question body', async () => {
    fetchEventSource.mockResolvedValue(undefined)

    await streamPaperQa('hss-001', '  trimmed?  ', {})

    expect(fetchEventSource).toHaveBeenCalledWith(
      '/api/v1/papers/hss-001/qa/stream',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify({ question: '  trimmed?  ' }),
      }),
    )
  })

  it('ignores empty SSE data lines and unknown events without crashing handlers', async () => {
    fetchEventSource.mockImplementation(
      async (
        _url: string,
        options: {
          onmessage?: (ev: { event?: string; data: string }) => void
        },
      ) => {
        options.onmessage?.({ event: 'message', data: '' })
        options.onmessage?.({ event: 'ping', data: '{}' })
        options.onmessage?.({ event: 'message', data: 'not-json' })
        options.onmessage?.({
          event: 'message',
          data: JSON.stringify({ delta: 'ok' }),
        })
      },
    )

    const deltas: string[] = []
    await streamPaperQa('hss-001', 'q', {
      onMessage: (data) => {
        deltas.push(data.delta)
      },
    })

    expect(deltas).toEqual(['ok'])
  })

  it('surfaces default error message when SSE error payload omits message', async () => {
    fetchEventSource.mockImplementation(
      async (
        _url: string,
        options: {
          onmessage?: (ev: { event?: string; data: string }) => void
        },
      ) => {
        options.onmessage?.({
          event: 'error',
          data: JSON.stringify({ code: 'QA_STREAM_ERROR' }),
        })
      },
    )

    let errorMessage = ''
    await streamPaperQa('hss-001', 'q', {
      onError: (message) => {
        errorMessage = message
      },
    })

    expect(errorMessage).toBe('SSE error')
  })

  it('dispatches all V2 citation types to onCitation handler', async () => {
    fetchEventSource.mockImplementation(
      async (
        _url: string,
        options: {
          onmessage?: (ev: { event?: string; data: string }) => void
        },
      ) => {
        const frames = [
          { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' },
          { type: 'edge', paper_id: 'hss-001', edge_id: 'e1', label: '分论点 → 核心论点' },
          {
            type: 'chunk',
            paper_id: 'hss-001',
            chunk_id: 'c1',
            label: '片段 c1',
            text_preview: '预览',
          },
          { type: 'page', paper_id: 'hss-001', page: 12, label: '第12页' },
        ]
        for (const data of frames) {
          options.onmessage?.({
            event: 'citation',
            data: JSON.stringify(data),
          })
        }
      },
    )

    const received: string[] = []
    await streamPaperQa('hss-001', 'detail question', {
      onCitation: (data) => {
        received.push(data.type)
      },
    })

    expect(received).toEqual(['node', 'edge', 'chunk', 'page'])
  })
})
