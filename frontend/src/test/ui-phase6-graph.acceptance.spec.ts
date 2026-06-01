/**
 * Phase 6 Graph acceptance (6.1–6.8) — design-spec §10 + ui-design-progress.
 */
import { describe, expect, it } from 'vitest'

import { GRAPH_BASELINE_COPY, GRAPH_DRAWER_WIDTH_PX } from '@/constants/graphCopy'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import {
  GRAPH_ACTIVE_LINE_WIDTH,
  GRAPH_COMPACT_HEIGHT,
  GRAPH_DEFAULT_HEIGHT,
  GRAPH_EDGE_STROKE,
  GRAPH_FULL_MIN_HEIGHT,
  GRAPH_HOVER_LINE_WIDTH,
  GRAPH_NODE_RADIUS,
  GRAPH_STATE_ANIMATION_MS,
  buildG6FitViewPadding,
  buildG6LayoutOptions,
  findGraphNodeById,
  getGraphNodeFillColor,
  getGraphNodeSnippet,
  getGraphNodeTypeColor,
} from '@/utils/paperGraph'

const graphViewSrc = readFrontendSource('views/PaperGraphView.vue')
const detailViewSrc = readFrontendSource('views/PaperDetailView.vue')
const paperGraphSrc = readFrontendSource('components/graph/PaperGraph.vue')
const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')
const graphToolbarSrc = readFrontendSource('components/graph/GraphToolbar.vue')
const graphLegendSrc = readFrontendSource('components/graph/GraphLegend.vue')
const graphDrawerSrc = readFrontendSource('components/graph/GraphNodeDrawer.vue')
const graphCopySrc = readFrontendSource('constants/graphCopy.ts')
const routerSrc = readFrontendSource('router/index.ts')

describe('Phase 6 Graph acceptance (6.1–6.8)', () => {
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

    it('uses tinted node fill + type stroke for readable labels in preview', () => {
      expect(paperGraphUtilSrc).toContain('getGraphNodeFillColor')
      expect(paperGraphUtilSrc).toContain('strokeColor')
      expect(paperGraphUtilSrc).toContain('labelFill')
      expect(getGraphNodeFillColor('AnalyticalLens', 'HSS')).not.toBe(getGraphNodeTypeColor('AnalyticalLens', 'HSS'))
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

  describe('6.5 Legend bottom-left overlay; caption 节点类型', () => {
    it('GraphLegend uses baseline caption and Graph view pins legend to stage corner', () => {
      expect(graphCopySrc).toContain(GRAPH_BASELINE_COPY.legendTitle)
      expect(GRAPH_BASELINE_COPY.legendTitle).toBe('节点类型')
      expect(graphLegendSrc).toContain('GRAPH_BASELINE_COPY.legendTitle')
      expect(graphLegendSrc).toContain('text-caption graph-legend__title')
      expect(graphViewSrc).toContain('GraphLegend')
      expect(graphViewSrc).toContain('graph-view__legend')
      expect(graphViewSrc).toContain('bottom: var(--spacing-16)')
      expect(graphViewSrc).toContain('left: var(--spacing-16)')
    })
  })

  describe('6.6 Drawer 320px, 250ms slide; label/type/snippet fields', () => {
    it('GraphNodeDrawer uses baseline field copy and slow transition token', () => {
      const tokens = loadDesignTokenMap()

      expect(GRAPH_DRAWER_WIDTH_PX).toBe(320)
      expect(tokens['--duration-slow']).toBe('250ms')
      expect(graphCopySrc).toContain(GRAPH_BASELINE_COPY.drawerFieldType)
      expect(graphCopySrc).toContain(GRAPH_BASELINE_COPY.drawerFieldSnippet)
      expect(graphDrawerSrc).toContain('GRAPH_DRAWER_WIDTH_PX')
      expect(graphDrawerSrc).toContain('var(--transition-slow)')
      expect(graphDrawerSrc).toContain('graph-node-drawer__label')
      expect(graphDrawerSrc).toContain('graph-node-drawer__type-badge')
      expect(graphDrawerSrc).toContain('graph-node-drawer__snippet')
      expect(graphViewSrc).toContain('GraphNodeDrawer')
    })
  })

  describe('6.7 ?node= deep-link activates node on entry', () => {
    it('PaperGraphView syncs route query to highlight and opens drawer after load', () => {
      expect(graphViewSrc).toContain('readNodeQueryFromRoute')
      expect(graphViewSrc).toContain('syncSelectionFromRoute')
      expect(graphViewSrc).toContain('route.query.node')
      expect(graphViewSrc).toContain(':highlight-node-id="highlightNodeId"')
      expect(graphViewSrc).toContain('syncSelectionFromRoute(true)')
      expect(paperGraphUtilSrc).toContain('findGraphNodeById')
      expect(findGraphNodeById).toBeDefined()
      expect(getGraphNodeSnippet).toBeDefined()
    })
  })

  describe('6.8 Error 409 graph-not-ready title + CTA back to detail', () => {
    it('shows baseline title and detail CTA only for GRAPH_NOT_READY', () => {
      expect(graphCopySrc).toContain(GRAPH_BASELINE_COPY.graphNotReadyTitle)
      expect(GRAPH_BASELINE_COPY.graphNotReadyTitle).toBe('图谱未就绪')
      expect(graphViewSrc).toContain('isGraphNotReadyError')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY.graphNotReadyTitle')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY.graphNotReadyCta')
      expect(graphViewSrc).toContain('v-if="isGraphNotReadyError"')
      expect(graphViewSrc).toContain('backToDetail')
    })
  })

  describe('§17 size conventions (design-spec code constants)', () => {
    it('Detail compact: design 480px readable area maps to GRAPH_COMPACT_HEIGHT = 320', () => {
      expect(GRAPH_COMPACT_HEIGHT).toBe(320)
      expect(paperGraphUtilSrc).toContain('GRAPH_COMPACT_HEIGHT = 320')
      expect(paperGraphSrc).toContain('GRAPH_COMPACT_HEIGHT')
      expect(paperGraphSrc).toContain('min-height: 320px')
      expect(detailViewSrc).toContain('compact')
      expect(detailViewSrc).toContain('min-height: 320px')
    })

    it('Graph preview wires dagre layout spacing and fitView padding helpers', () => {
      expect(paperGraphUtilSrc).toContain('buildG6LayoutOptions')
      expect(paperGraphUtilSrc).toContain('buildG6FitViewPadding')
      expect(paperGraphSrc).toContain('buildG6LayoutOptions')
      expect(paperGraphSrc).toContain('fitGraphView')
      expect(paperGraphSrc).toContain('fitView')
      expect(buildG6LayoutOptions({ compact: true, nodeCount: 3 }).nodesep).toBeGreaterThan(36)
      expect(buildG6FitViewPadding({ compact: true })).toEqual([24, 24, 100, 24])
    })

    it('Graph full screen: DEFAULT_HEIGHT 480 + ResizeObserver resize with 720px floor', () => {
      expect(GRAPH_DEFAULT_HEIGHT).toBe(480)
      expect(GRAPH_FULL_MIN_HEIGHT).toBe(720)
      expect(paperGraphUtilSrc).toContain('GRAPH_DEFAULT_HEIGHT = 480')
      expect(paperGraphUtilSrc).toContain('GRAPH_FULL_MIN_HEIGHT = 720')
      expect(paperGraphSrc).toContain('GRAPH_DEFAULT_HEIGHT')
      expect(paperGraphSrc).toContain('GRAPH_FULL_MIN_HEIGHT')
      expect(paperGraphSrc).toContain('ResizeObserver')
      expect(paperGraphSrc).toContain('resizeGraph')
      expect(paperGraphSrc).toContain('min-height: 480px')
      expect(paperGraphSrc).toContain('min-height: 720px')
      expect(graphViewSrc).toContain('min-height: 720px')
    })
  })

  describe('Phase 6 acceptance checklist (ui-design-progress §验收 6.1–6.8)', () => {
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

    it('regression gate: unit specs cover Graph view, legend, drawer, toolbar, sizes, and G6 helpers', () => {
      const graphViewSpecSrc = readFrontendSource('views/PaperGraphView.spec.ts')
      const paperGraphSpecSrc = readFrontendSource('components/graph/PaperGraph.spec.ts')
      const graphToolbarSpecSrc = readFrontendSource('components/graph/GraphToolbar.spec.ts')
      const graphLegendSpecSrc = readFrontendSource('components/graph/GraphLegend.spec.ts')
      const graphDrawerSpecSrc = readFrontendSource('components/graph/GraphNodeDrawer.spec.ts')
      const paperGraphTestSrc = readFrontendSource('utils/paperGraph.test.ts')

      expect(graphViewSpecSrc).toContain('canvas-first full-bleed stage')
      expect(graphViewSpecSrc).toContain('opens node drawer when a graph node is clicked')
      expect(graphViewSpecSrc).toContain('shows generic error without CTA')
      expect(paperGraphSpecSrc).toContain('configures rect nodes with type colors')
      expect(paperGraphSpecSrc).toContain('calls fitView after render on init')
      expect(paperGraphSpecSrc).toContain('§17 viewport height conventions')
      expect(paperGraphSpecSrc).toContain('ResizeObserver')
      expect(graphToolbarSpecSrc).toContain('emits toolbar actions')
      expect(graphLegendSpecSrc).toContain('renders baseline caption')
      expect(graphDrawerSpecSrc).toContain('320px width and 250ms slide transition token')
      expect(paperGraphTestSrc).toContain('findGraphNodeById returns node')
      expect(paperGraphTestSrc).toContain('graph preview viewport + layout helpers (D)')
      expect(paperGraphTestSrc).toContain('graph node label contrast + edge label chrome (D)')
      expect(paperGraphTestSrc).toContain('§17 graph viewport size constants')
    })

    it('§17 size constants are exported from paperGraph.ts and wired in PaperGraph.vue', () => {
      expect(GRAPH_COMPACT_HEIGHT).toBe(320)
      expect(GRAPH_DEFAULT_HEIGHT).toBe(480)
      expect(GRAPH_FULL_MIN_HEIGHT).toBe(720)
      expect(paperGraphSrc).toContain('graphHeight()')
      expect(paperGraphSrc).toContain('Math.max(GRAPH_FULL_MIN_HEIGHT')
    })
  })
})
