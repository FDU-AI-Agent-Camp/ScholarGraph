import { describe, expect, it } from 'vitest'

import type { QaStreamCitationData } from '@/api/types'
import {
  appendUniqueCitation,
  citationDisplayId,
  citationKey,
  citationNodeId,
  isNodeCitation,
  nodeCitation,
} from '@/utils/qaCitations'

describe('qaCitations helpers', () => {
  const node = nodeCitation('hss-001', 'n1', '核心论点')
  const edge: QaStreamCitationData = {
    type: 'edge',
    paper_id: 'hss-001',
    edge_id: 'e1',
    label: '分论点 → 核心论点',
  }
  const chunk: QaStreamCitationData = {
    type: 'chunk',
    paper_id: 'hss-001',
    chunk_id: 'c1',
    label: '片段 c1',
    text_preview: '预览文本',
  }
  const page: QaStreamCitationData = {
    type: 'page',
    paper_id: 'hss-001',
    page: 12,
    label: '第12页',
  }

  it('nodeCitation builds typed node payload', () => {
    expect(node).toEqual({
      type: 'node',
      paper_id: 'hss-001',
      node_id: 'n1',
      label: '核心论点',
    })
    expect(isNodeCitation(node)).toBe(true)
    expect(isNodeCitation(edge)).toBe(false)
  })

  it('citationDisplayId returns ref id per type', () => {
    expect(citationDisplayId(node)).toBe('n1')
    expect(citationDisplayId(edge)).toBe('e1')
    expect(citationDisplayId(chunk)).toBe('c1')
    expect(citationDisplayId(page)).toBe('12')
  })

  it('citationKey encodes paper_id, type, and ref id', () => {
    expect(citationKey(node)).toBe('hss-001:node:n1')
    expect(citationKey(edge)).toBe('hss-001:edge:e1')
    expect(citationKey(chunk)).toBe('hss-001:chunk:c1')
    expect(citationKey(page)).toBe('hss-001:page:12')
  })

  it('citationNodeId returns node_id only for node citations', () => {
    expect(citationNodeId(node)).toBe('n1')
    expect(citationNodeId(edge)).toBeNull()
  })

  it('appendUniqueCitation deduplicates by citationKey across types', () => {
    let citations = appendUniqueCitation([], node)
    citations = appendUniqueCitation(citations, edge)
    citations = appendUniqueCitation(citations, chunk)
    citations = appendUniqueCitation(citations, page)
    expect(citations).toHaveLength(4)
    expect(appendUniqueCitation(citations, node)).toHaveLength(4)
    expect(appendUniqueCitation(citations, edge)).toHaveLength(4)
  })
})
