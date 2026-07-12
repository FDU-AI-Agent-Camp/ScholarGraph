import { describe, expect, it } from 'vitest'

import qaStreamV2Frames from '../../../docs/api/fixtures/qa-stream-v2-frames.json'
import { parseQaStreamEvent } from '@/api/qaStream'

describe('parseQaStreamEvent', () => {
  it('parses message events', () => {
    const event = parseQaStreamEvent('message', JSON.stringify({ delta: '你好' }))
    expect(event).toEqual({ type: 'message', data: { delta: '你好' } })
  })

  it('parses V2 node citation events', () => {
    const event = parseQaStreamEvent(
      'citation',
      JSON.stringify({ type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }),
    )
    expect(event).toEqual({
      type: 'citation',
      data: { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' },
    })
  })

  it('parses V1 citation without type as node', () => {
    const event = parseQaStreamEvent(
      'citation',
      JSON.stringify({ type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }),
    )
    expect(event).toEqual({
      type: 'citation',
      data: { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' },
    })
  })

  it('parses edge, chunk, and page citation events', () => {
    const edge = parseQaStreamEvent(
      'citation',
      JSON.stringify({
        type: 'edge',
        paper_id: 'hss-001',
        edge_id: 'e1',
        label: '分论点 → 核心论点',
      }),
    )
    expect(edge).toEqual({
      type: 'citation',
      data: { type: 'edge', paper_id: 'hss-001', edge_id: 'e1', label: '分论点 → 核心论点' },
    })

    const chunk = parseQaStreamEvent(
      'citation',
      JSON.stringify({
        type: 'chunk',
        paper_id: 'hss-001',
        chunk_id: 'c1',
        label: '片段 c1',
        text_preview: '预览',
        preview_state: 'ready',
      }),
    )
    expect(chunk?.type).toBe('citation')
    if (chunk?.type === 'citation') {
      expect(chunk.data).toEqual({
        type: 'chunk',
        paper_id: 'hss-001',
        chunk_id: 'c1',
        label: '片段 c1',
        text_preview: '预览',
        preview_state: 'ready',
      })
    }

    const page = parseQaStreamEvent(
      'citation',
      JSON.stringify({ type: 'page', paper_id: 'hss-001', page: 12, label: '第12页' }),
    )
    expect(page?.type).toBe('citation')
    if (page?.type === 'citation') {
      expect(page.data).toEqual({ type: 'page', paper_id: 'hss-001', page: 12, label: '第12页' })
    }
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

  it('coerces missing node citation fields to empty strings', () => {
    const event = parseQaStreamEvent('citation', JSON.stringify({ paper_id: 'hss-001' }))
    expect(event).toEqual({
      type: 'citation',
      data: { type: 'node', paper_id: 'hss-001', node_id: '', label: '' },
    })
  })

  it('returns null for unknown citation type', () => {
    expect(parseQaStreamEvent('citation', JSON.stringify({ type: 'unknown', paper_id: 'hss-001' }))).toBeNull()
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

  it('parses canonical qa-stream-v2-frames fixture', () => {
    const parsed = qaStreamV2Frames.map((frame) => parseQaStreamEvent(frame.event, JSON.stringify(frame.data)))
    expect(parsed.every((item) => item !== null)).toBe(true)
    const types = parsed
      .filter((item) => item?.type === 'citation')
      .map((item) => (item?.type === 'citation' ? item.data.type : null))
    expect(types).toEqual(['node', 'edge', 'chunk', 'page'])
  })
})
