import { describe, expect, it } from 'vitest'

import { parseQaStreamEvent } from '@/api/qaStream'

describe('parseQaStreamEvent', () => {
  it('parses message events', () => {
    const event = parseQaStreamEvent('message', JSON.stringify({ delta: '你好' }))
    expect(event).toEqual({ type: 'message', data: { delta: '你好' } })
  })

  it('parses citation events', () => {
    const event = parseQaStreamEvent(
      'citation',
      JSON.stringify({ paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }),
    )
    expect(event).toEqual({
      type: 'citation',
      data: { paper_id: 'hss-001', node_id: 'n1', label: '核心论点' },
    })
  })

  it('parses done events with optional answer', () => {
    const event = parseQaStreamEvent('done', JSON.stringify({ answer_id: 'ans-1', answer: '完整回答' }))
    expect(event).toEqual({
      type: 'done',
      data: { answer_id: 'ans-1', answer: '完整回答' },
    })
  })

  it('parses error events', () => {
    const event = parseQaStreamEvent('error', JSON.stringify({ code: 'QA_FAILED', message: '图谱未就绪' }))
    expect(event).toEqual({
      type: 'error',
      data: { code: 'QA_FAILED', message: '图谱未就绪' },
    })
  })

  it('returns null for unknown events or invalid JSON', () => {
    expect(parseQaStreamEvent('ping', '{}')).toBeNull()
    expect(parseQaStreamEvent('message', 'not-json')).toBeNull()
    expect(parseQaStreamEvent('message', 'null')).toBeNull()
  })

  it('coerces missing citation fields to empty strings', () => {
    const event = parseQaStreamEvent('citation', JSON.stringify({ paper_id: 'hss-001' }))
    expect(event).toEqual({
      type: 'citation',
      data: { paper_id: 'hss-001', node_id: '', label: '' },
    })
  })

  it('defaults error message when payload omits message', () => {
    const event = parseQaStreamEvent('error', JSON.stringify({ code: 'QA_STREAM_ERROR' }))
    expect(event).toEqual({
      type: 'error',
      data: { code: 'QA_STREAM_ERROR', message: 'SSE error' },
    })
  })

  it('treats non-object JSON as unparseable', () => {
    expect(parseQaStreamEvent('message', '"just-a-string"')).toBeNull()
    expect(parseQaStreamEvent('message', '42')).toBeNull()
  })

  it('exhaustive switch coverage for all event types', () => {
    const events = ['message', 'citation', 'done', 'error'] as const
    for (const name of events) {
      const parsed = parseQaStreamEvent(
        name,
        name === 'message'
          ? '{"delta":"x"}'
          : name === 'citation'
            ? '{"paper_id":"p","node_id":"n","label":"l"}'
            : name === 'done'
              ? '{"answer_id":"a"}'
              : '{"message":"err"}',
      )
      expect(parsed?.type).toBe(name)
    }
  })
})
