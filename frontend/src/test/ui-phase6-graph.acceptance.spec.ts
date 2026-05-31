/**
 * Phase 6 Graph acceptance (6.1–6.4) — design-spec §10 + ui-design-progress.
 */
import { describe, expect, it } from 'vitest'

import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import {
  GRAPH_ACTIVE_LINE_WIDTH,
  GRAPH_EDGE_STROKE,
  GRAPH_HOVER_LINE_WIDTH,
  GRAPH_NODE_RADIUS,
  GRAPH_STATE_ANIMATION_MS,
  getGraphNodeTypeColor,
} from '@/utils/paperGraph'

const graphViewSrc = readFrontendSource('views/PaperGraphView.vue')
const paperGraphSrc = readFrontendSource('components/graph/PaperGraph.vue')
const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')
const graphToolbarSrc = readFrontendSource('components/graph/GraphToolbar.vue')
const graphCopySrc = readFrontendSource('constants/graphCopy.ts')
const routerSrc = readFrontendSource('router/index.ts')

describe('Phase 6 Graph acceptance (6.1–6.4)', () => {
  describe('6.1 full-bleed canvas #F1F5F9', () => {
    it('routes graph page as fullBleed and uses canvas background on stage', () => {
      const tokens = loadDesignTokenMap()

      expect(routerSrc).toContain('fullBleed: true')
      expect(tokens['--color-bg-canvas']).toBe('#f1f5f9')
      expect(graphViewSrc).toContain('graph-view__stage')
      expect(graphViewSrc).toContain('var(--color-bg-canvas)')
      expect(graphViewSrc).toContain('min-height: 720px')
      expect(paperGraphSrc).toContain('fullBleed')
      expect(paperGraphSrc).toContain('graph-host--full-bleed')
    })
  })

  describe('6.2 rounded rect nodes and type color table', () => {
    it('maps HSS/STEM node types through paperGraph.ts palette', () => {
      expect(paperGraphUtilSrc).toContain('HSS_NODE_TYPE_COLORS')
      expect(paperGraphUtilSrc).toContain('STEM_NODE_TYPE_COLORS')
      expect(paperGraphUtilSrc).toContain("type: 'rect'")
      expect(getGraphNodeTypeColor('Thesis', 'HSS')).toBe('#0d6e6e')
      expect(getGraphNodeTypeColor('Method', 'STEM')).toBe('#2563eb')
      expect(paperGraphSrc).toContain('buildG6GraphData')
    })

    it('uses 8px corner radius on rect nodes', () => {
      expect(paperGraphUtilSrc).toContain('GRAPH_NODE_RADIUS')
      expect(GRAPH_NODE_RADIUS).toBe(8)
    })
  })

  describe('6.3 hover stroke 120ms without displacement; active #E11D48 3px', () => {
    it('defines separate hover/active states and 120ms stroke animation', () => {
      const tokens = loadDesignTokenMap()

      expect(paperGraphUtilSrc).toContain('hover: {')
      expect(paperGraphUtilSrc).toContain('active: {')
      expect(GRAPH_HOVER_LINE_WIDTH).toBe(2)
      expect(GRAPH_ACTIVE_LINE_WIDTH).toBe(3)
      expect(GRAPH_STATE_ANIMATION_MS).toBe(120)
      expect(tokens['--duration-instant']).toBe('120ms')
      expect(tokens['--color-citation-active']).toBe('#e11d48')
      expect(paperGraphUtilSrc).toContain('hover-activate')
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\.05/)
      expect(paperGraphUtilSrc).toContain("fields: ['stroke', 'lineWidth', 'fill']")
      expect(GRAPH_EDGE_STROKE).toBe('#94a3b8')
    })
  })

  describe('6.4 toolbar surface + shadow-md; button hover 120ms', () => {
    it('GraphToolbar uses baseline copy and design-spec chrome', () => {
      expect(graphCopySrc).toContain(GRAPH_BASELINE_COPY.toolbarZoomIn)
      expect(graphViewSrc).toContain('GraphToolbar')
      expect(graphViewSrc).toContain('graph-view__toolbar')
      expect(graphToolbarSrc).toContain('var(--color-bg-surface)')
      expect(graphToolbarSrc).toContain('var(--shadow-md)')
      expect(graphToolbarSrc).toContain('var(--transition-instant)')
      expect(graphToolbarSrc).toContain('width: 36px')
    })
  })

  describe('Phase 6 acceptance checklist (ui-design-progress §验收 6.1–6.4)', () => {
    it('§1.4.1 canvas #F1F5F9 full-bleed stage is wired end-to-end', () => {
      const tokens = loadDesignTokenMap()

      expect(tokens['--color-bg-canvas']).toBe('#f1f5f9')
      expect(graphViewSrc).toContain(':full-bleed="true"')
      expect(graphViewSrc).toContain('min-height: 720px')
    })

    it('§1.4.3 hover/active stroke uses 120ms budget without scale displacement', () => {
      expect(paperGraphUtilSrc).toContain('GRAPH_STATE_ANIMATION_MS')
      expect(GRAPH_STATE_ANIMATION_MS).toBe(120)
      expect(paperGraphUtilSrc).toContain('hover-activate')
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\.05/)
    })

    it('active stroke matches Citation Tag token via resolvePaperGraphThemeTokens', () => {
      const tokens = loadDesignTokenMap()

      expect(tokens['--color-citation-active']).toBe('#e11d48')
      expect(paperGraphUtilSrc).toContain('resolvePaperGraphThemeTokens')
    })

    it('regression gate: unit specs cover Graph view, toolbar, and G6 helpers', () => {
      const graphViewSpecSrc = readFrontendSource('views/PaperGraphView.spec.ts')
      const paperGraphSpecSrc = readFrontendSource('components/graph/PaperGraph.spec.ts')
      const graphToolbarSpecSrc = readFrontendSource('components/graph/GraphToolbar.spec.ts')
      const paperGraphTestSrc = readFrontendSource('utils/paperGraph.test.ts')

      expect(graphViewSpecSrc).toContain('canvas-first full-bleed stage')
      expect(graphViewSpecSrc).toContain('disables toolbar while graph fetch fails')
      expect(paperGraphSpecSrc).toContain('configures rect nodes with type colors')
      expect(graphToolbarSpecSrc).toContain('emits toolbar actions')
      expect(paperGraphTestSrc).toContain('buildG6GraphData attaches paradigm fill')
    })
  })
})
