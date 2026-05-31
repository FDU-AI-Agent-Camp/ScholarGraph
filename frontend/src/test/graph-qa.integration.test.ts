/**
 * Graph + QA SSE integration: fixture graph ↔ G6 payload ↔ citation highlight.
 */
import { describe, expect, it } from 'vitest'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { UnifiedPaperGraph } from '@/api/types'
import { cssToken } from '@/utils/cssTokens'
import { appendUniqueCitation, buildHighlightStateMap, toG6GraphPayload } from '@/utils/paperGraph'
import { DESIGN_SPEC_SEMANTIC_COLORS, loadDesignTokenMap } from '@/test/helpers/designTokens'

describe('graph + QA SSE integration (fixtures)', () => {
  it('chains SSE citation event into highlight state for graph-hss nodes', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const citationEvent = parseQaStreamEvent(
      'citation',
      JSON.stringify({ paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }),
    )
    expect(citationEvent?.type).toBe('citation')
    if (citationEvent?.type !== 'citation') {
      return
    }

    const citations = appendUniqueCitation([], citationEvent.data)
    const nodeIds = toG6GraphPayload(graph).nodes.map((node) => node.id)
    const lastCitation = citations[citations.length - 1]
    const highlight = buildHighlightStateMap(nodeIds, lastCitation?.node_id)

    expect(highlight.n1).toBe('active')
    expect(highlight.n2).toEqual([])
  })

  it('deduplicates repeated citation SSE frames during one answer stream', () => {
    const payload = JSON.stringify({ paper_id: 'hss-001', node_id: 'n1', label: '核心论点' })
    const first = parseQaStreamEvent('citation', payload)
    const second = parseQaStreamEvent('citation', payload)
    expect(first?.type).toBe('citation')
    expect(second?.type).toBe('citation')
    if (first?.type !== 'citation' || second?.type !== 'citation') {
      return
    }

    let citations = appendUniqueCitation([], first.data)
    citations = appendUniqueCitation(citations, second.data)
    expect(citations).toHaveLength(1)
  })

  it('uses the same citation active token as TagCitation / PaperGraph (#E11D48)', () => {
    const tokens = loadDesignTokenMap()
    expect(tokens['--color-citation-active']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.citationActive)
    expect(cssToken('--color-citation-active', '#e11d48')).toBe('#e11d48')
  })
})
