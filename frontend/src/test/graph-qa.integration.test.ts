/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Graph + QA SSE integration: fixture graph ↔ G6 payload ↔ citation highlight.
 */
import { describe, expect, it } from 'vitest'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { UnifiedPaperGraph } from '@/api/types'
import { cssToken } from '@/utils/cssTokens'
import { appendUniqueCitation, buildHighlightStateMap, toG6GraphPayload } from '@/utils/paperGraph'
import { citationNodeId } from '@/utils/qaCitations'
import { DESIGN_SPEC_SEMANTIC_COLORS, loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import { answerPanelTypographyMatchesBaseline, citationTagMixedLayout } from '@/test/helpers/copyDiscipline'
import { answerPanelStyleBlockHasNoAnimation, extractStyleBlocks } from '@/test/helpers/motionDiscipline'

describe('graph + QA SSE integration (fixtures)', () => {
  it('chains SSE citation event into highlight state for graph-hss nodes', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const citationEvent = parseQaStreamEvent(
      'citation',
      JSON.stringify({ type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }),
    )
    expect(citationEvent?.type).toBe('citation')
    if (citationEvent?.type !== 'citation') {
      return
    }

    const citations = appendUniqueCitation([], citationEvent.data)
    const nodeIds = toG6GraphPayload(graph).nodes.map((node) => node.id)
    const lastCitation = citations[citations.length - 1]
    const highlight = buildHighlightStateMap(nodeIds, citationNodeId(lastCitation!))

    expect(highlight.n1).toBe('active')
    expect(highlight.n2).toEqual([])
  })

  it('deduplicates repeated citation SSE frames during one answer stream', () => {
    const payload = JSON.stringify({ type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' })
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

  it('maps Detail answer panel to §1.4.1 subtle surface token #FAFBFC', () => {
    const tokens = loadDesignTokenMap()
    const detailSrc = readFrontendSource('views/PaperDetailView.vue')

    expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
    expect(detailSrc).toContain('detail-qa__answer-panel')
    expect(detailSrc).toContain('var(--color-bg-subtle)')
    expect(detailSrc).toContain('text-body-lg')
  })

  it('keeps TagCitation active transition within 150ms motion budget', () => {
    const tokens = loadDesignTokenMap()
    const tagSrc = readFrontendSource('components/ui/TagCitation.vue')

    expect(tokens['--duration-fast']).toBe('150ms')
    expect(tokens['--transition-fast']).toContain('var(--duration-fast)')
    expect(tagSrc).toContain('tag-citation--active')
    expect(tagSrc).toContain('var(--transition-fast)')
  })

  it('switches graph highlight when user selects another cited node', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const nodeIds = toG6GraphPayload(graph).nodes.map((node) => node.id)

    const firstCitation = { type: 'node' as const, paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }
    const secondCitation = { type: 'node' as const, paper_id: 'hss-001', node_id: 'n2', label: '分论点' }

    let citations = appendUniqueCitation([], firstCitation)
    citations = appendUniqueCitation(citations, secondCitation)

    let highlightNodeId = citationNodeId(citations[citations.length - 1]!)
    let states = buildHighlightStateMap(nodeIds, highlightNodeId)
    expect(states.n2).toBe('active')
    expect(states.n1).toEqual([])

    highlightNodeId = citationNodeId(citations[0]!)
    states = buildHighlightStateMap(nodeIds, highlightNodeId)
    expect(states.n1).toBe('active')
    expect(states.n2).toEqual([])
  })

  it('wires Detail view citation click and graph node-click to shared highlightNodeId', () => {
    const detailSrc = readFrontendSource('views/PaperDetailView.vue')
    const qaComposableSrc = readFrontendSource('composables/usePaperDetailQa.ts')

    expect(qaComposableSrc).toContain('const highlightNodeId = ref')
    expect(detailSrc).toContain("item.type === 'node' && item.node_id === highlightNodeId")
    expect(detailSrc).toContain('@click="focusCitation(item)"')
    expect(detailSrc).toContain(':highlight-node-id="highlightNodeId"')
    expect(qaComposableSrc).toContain('function onGraphNodeClick')
    expect(detailSrc).toContain('onGraphNodeClick')
  })

  it('shares citation active tokens between TagCitation and full Graph theme helpers', () => {
    const tokens = loadDesignTokenMap()
    const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')

    expect(tokens['--color-citation-active']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.citationActive)
    expect(paperGraphUtilSrc).toContain('resolvePaperGraphThemeTokens')
    expect(paperGraphUtilSrc).toContain("'--color-citation-active'")
  })

  describe('§1.4.3 motion acceptance checklist', () => {
    it('applies graph active state within 150ms budget when citation node_id is selected', () => {
      const tokens = loadDesignTokenMap()
      const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')
      const durationFastMs = Number.parseInt(tokens['--duration-fast'] ?? '150', 10)

      expect(paperGraphUtilSrc).toContain('GRAPH_STATE_ANIMATION_MS')
      expect(paperGraphUtilSrc).toContain('buildHighlightStateMap')
      expect(durationFastMs).toBe(150)
    })

    it('keeps TagCitation and graph utils free of transition:all', () => {
      const tagStyles = readFrontendSource('components/ui/TagCitation.vue')
      const graphUtilSrc = readFrontendSource('utils/paperGraph.ts')

      expect(tagStyles).not.toMatch(/transition\s*:\s*all\b/i)
      expect(graphUtilSrc).not.toMatch(/transition\s*:\s*all\b/i)
    })

    it('preserves readable node labels and static answer panel during SSE demo path', () => {
      const detailSrc = readFrontendSource('views/PaperDetailView.vue')
      const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')

      expect(detailSrc).toContain('detail-qa__answer-panel')
      expect(detailSrc).toContain('text-body-lg')
      expect(answerPanelStyleBlockHasNoAnimation(extractStyleBlocks(detailSrc))).toBe(true)
      expect(paperGraphUtilSrc).toContain('labelFill')
      expect(paperGraphUtilSrc).not.toMatch(/\btranslate\s*\(/i)
    })
  })

  describe('§1.4.4 typography acceptance checklist', () => {
    it('SSE answer panel keeps Body-lg + pre-wrap + subtle surface for long answers', () => {
      const detailSrc = readFrontendSource('views/PaperDetailView.vue')
      expect(answerPanelTypographyMatchesBaseline(detailSrc, extractStyleBlocks(detailSrc))).toBe(true)
    })

    it('Citation Tag keeps label sans + (node_id) mono for QA ↔ graph path', () => {
      const tagSrc = readFrontendSource('components/ui/TagCitation.vue')
      expect(citationTagMixedLayout(tagSrc)).toBe(true)
    })

    it('graph QA path does not force answer body into mono', () => {
      const detailStyles = extractStyleBlocks(readFrontendSource('views/PaperDetailView.vue'))
      expect(detailStyles).not.toMatch(/\.detail-qa__answer-text[\s\S]*font-family: var\(--font-mono\)/)
    })
  })
})
