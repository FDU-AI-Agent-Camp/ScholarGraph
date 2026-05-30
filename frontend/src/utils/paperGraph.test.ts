import { describe, expect, it } from 'vitest'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import type { UnifiedPaperGraph } from '@/api/types'

import { buildHighlightStateMap, citationKey, toG6GraphPayload } from './paperGraph'

describe('citationKey', () => {
  it('joins paper_id and node_id for stable list keys', () => {
    expect(citationKey({ paper_id: 'hss-001', node_id: 'n_lens', label: '历史制度主义' })).toBe('hss-001:n_lens')
  })
})

describe('graph-hss fixture parity', () => {
  const graph = graphFixture.data as UnifiedPaperGraph

  it('maps fixture nodes to G6 payload with nodeType', () => {
    const payload = toG6GraphPayload(graph)
    const thesis = payload.nodes.find((node) => node.id === 'n1')
    expect(thesis?.data.nodeType).toBe('Thesis')
    expect(payload.edges[0]?.data.edgeType).toBe('SUB_ARGUMENT_OF')
  })

  it('highlights AnalyticalLens node from fixture for citation UX', () => {
    const nodeIds = graph.nodes.map((node) => node.id)
    const states = buildHighlightStateMap(nodeIds, 'n_lens')
    expect(states.n_lens).toBe('active')
    expect(states.n1).toEqual([])
  })
})
