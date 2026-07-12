import { describe, expect, it } from 'vitest'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import type { UnifiedPaperGraph } from '@/api/types'

import {
  buildG6EdgeStyleOptions,
  buildG6FitViewPadding,
  buildG6GraphData,
  buildG6LayoutOptions,
  buildG6NodeStyleOptions,
  buildHighlightStateMap,
  citationKey,
  estimateGraphNodeSize,
  findGraphNodeById,
  getGraphNodeFillColor,
  getGraphNodeSnippet,
  getGraphNodeTypeColor,
  listGraphLegendEntries,
  listGraphNodeTypeStrokeColors,
  mixHexColors,
  resolvePaperGraphThemeTokens,
  toG6GraphPayload,
  GRAPH_EDGE_STROKE,
  GRAPH_FIT_VIEW_PADDING_COMPACT,
  GRAPH_FIT_VIEW_PADDING_DEFAULT,
  GRAPH_COMPACT_HEIGHT,
  GRAPH_DEFAULT_HEIGHT,
  GRAPH_FULL_MIN_HEIGHT,
  GRAPH_LAYOUT_COMPACT_NODESEP,
  GRAPH_LAYOUT_COMPACT_RANKSEP,
  GRAPH_LAYOUT_DEFAULT_NODESEP,
  GRAPH_LAYOUT_DEFAULT_RANKSEP,
  GRAPH_NODE_MIN_WIDTH,
  GRAPH_NODE_MAX_WIDTH,
  GRAPH_NODE_SURFACE_FILL,
  GRAPH_NODE_FILL_TINT_RATIO,
  buildG6Behaviors,
} from './paperGraph'

describe('citationKey', () => {
  it('joins paper_id, type, and ref id for stable list keys', () => {
    expect(citationKey({ type: 'node', paper_id: 'hss-001', node_id: 'n_lens', label: '历史制度主义' })).toBe(
      'hss-001:node:n_lens',
    )
  })
})

describe('graph-hss fixture parity', () => {
  const graph = graphFixture.data as UnifiedPaperGraph

  it('maps fixture nodes to G6 payload with nodeType', () => {
    const payload = toG6GraphPayload(graph)
    const thesis = payload.nodes.find((node) => node.id === 'n1')
    expect(thesis?.data.nodeType).toBe('Thesis')
    expect(payload.edges[0]?.data.edgeType).toBe('SUB_ARGUMENT_OF')
    expect(payload.edges.some((edge) => edge.source === 'n_lens')).toBe(true)
  })

  it('highlights AnalyticalLens node from fixture for citation UX', () => {
    const nodeIds = graph.nodes.map((node) => node.id)
    const states = buildHighlightStateMap(nodeIds, 'n_lens')
    expect(states.n_lens).toBe('active')
    expect(states.n1).toEqual([])
  })
})

describe('listGraphLegendEntries', () => {
  const graph = graphFixture.data as UnifiedPaperGraph

  it('returns unique node types with paradigm colors for compact legend', () => {
    const entries = listGraphLegendEntries(graph)
    const types = entries.map((entry) => entry.type)

    expect(new Set(types).size).toBe(types.length)
    expect(entries.length).toBeGreaterThan(0)
    expect(entries[0]?.color).toBe(getGraphNodeTypeColor(entries[0]!.type, graph.paradigm))
  })
})

describe('graph node sizing and G6 style helpers', () => {
  it('clamps rect node width between 80 and 140', () => {
    const [shortWidth] = estimateGraphNodeSize('短')
    const [longWidth] = estimateGraphNodeSize('这是一个非常非常长的节点标签用于测试最大宽度')

    expect(shortWidth).toBeGreaterThanOrEqual(GRAPH_NODE_MIN_WIDTH)
    expect(longWidth).toBeLessThanOrEqual(GRAPH_NODE_MAX_WIDTH)
  })

  it('buildG6NodeStyleOptions wires hover/active stroke tokens', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const options = buildG6NodeStyleOptions(theme, () => 'label')

    expect(options.type).toBe('rect')
    expect(options.state.active.stroke).toBe('#e11d48')
    expect(options.state.hover.lineWidth).toBe(2)
    expect(options.state.active.lineWidth).toBe(3)
  })

  it('buildG6GraphData attaches tinted fill, type stroke, and clamped size to each node', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const payload = buildG6GraphData(graph)
    const thesis = payload.nodes.find((node) => node.id === 'n1')

    expect(thesis?.data.fill).toBe(getGraphNodeFillColor('Thesis', 'HSS'))
    expect(thesis?.data.strokeColor).toBe(getGraphNodeTypeColor('Thesis', 'HSS'))
    expect(Array.isArray(thesis?.data.size)).toBe(true)
    const [width, height] = thesis?.data.size as [number, number]
    expect(width).toBeGreaterThanOrEqual(GRAPH_NODE_MIN_WIDTH)
    expect(width).toBeLessThanOrEqual(GRAPH_NODE_MAX_WIDTH)
    expect(height).toBeGreaterThanOrEqual(40)
  })

  it('buildG6NodeStyleOptions uses readable labelFill and per-type stroke from node data', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const options = buildG6NodeStyleOptions(theme, () => 'label')

    expect(options.style.labelFill).toBe('#111827')
    expect(typeof options.style.stroke).toBe('function')
  })

  it('buildG6EdgeStyleOptions exposes centered labels with background padding', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const edgeOptions = buildG6EdgeStyleOptions(theme)

    expect(edgeOptions.style.stroke).toBe(GRAPH_EDGE_STROKE)
    expect(edgeOptions.style.lineWidth).toBe(1)
    expect(edgeOptions.style.endArrow).toBe(true)
    expect(edgeOptions.style.labelPlacement).toBe('center')
    expect(edgeOptions.style.labelBackground).toBe(true)
    expect(edgeOptions.style.labelAutoRotate).toBe(false)
    expect(edgeOptions.style.labelFill).toBe('#6b7280')
  })

  it('buildG6LayoutOptions widens compact spacing and scales ranksep for large graphs', () => {
    expect(buildG6LayoutOptions({ compact: true, nodeCount: 3 })).toEqual({
      type: 'dagre',
      rankdir: 'TB',
      nodesep: GRAPH_LAYOUT_COMPACT_NODESEP,
      ranksep: GRAPH_LAYOUT_COMPACT_RANKSEP,
    })
    expect(buildG6LayoutOptions({ compact: false, nodeCount: 3 }).nodesep).toBe(GRAPH_LAYOUT_DEFAULT_NODESEP)
    expect(buildG6LayoutOptions({ compact: false, nodeCount: 12 }).ranksep).toBe(GRAPH_LAYOUT_DEFAULT_RANKSEP + 16)
  })

  it('buildG6FitViewPadding reserves compact bottom space for legend overlay', () => {
    expect(buildG6FitViewPadding({ compact: true })).toEqual(GRAPH_FIT_VIEW_PADDING_COMPACT)
    expect(buildG6FitViewPadding({ compact: false, fullBleed: true })).toBe(GRAPH_FIT_VIEW_PADDING_DEFAULT)
  })

  it('mixHexColors tints surface fill toward node type accent (helper retained for tokens)', () => {
    const tinted = mixHexColors(GRAPH_NODE_SURFACE_FILL, '#7c3aed', 0.12)
    expect(tinted).not.toBe('#7c3aed')
    expect(getGraphNodeFillColor('AnalyticalLens', 'HSS')).toBe(GRAPH_NODE_SURFACE_FILL)
  })

  it('listGraphNodeTypeStrokeColors exposes palette for contrast audits', () => {
    expect(listGraphNodeTypeStrokeColors('HSS')).toContain('#0d6e6e')
    expect(listGraphNodeTypeStrokeColors('STEM')).toContain('#2563eb')
  })
})

describe('graph preview viewport + layout helpers (D)', () => {
  it('buildG6LayoutOptions uses dagre TB with compact vs default spacing constants', () => {
    expect(buildG6LayoutOptions({ compact: true, nodeCount: 2 })).toMatchObject({
      type: 'dagre',
      rankdir: 'TB',
      nodesep: GRAPH_LAYOUT_COMPACT_NODESEP,
      ranksep: GRAPH_LAYOUT_COMPACT_RANKSEP,
    })
    expect(buildG6LayoutOptions({ compact: false, nodeCount: 2 })).toMatchObject({
      type: 'dagre',
      rankdir: 'TB',
      nodesep: GRAPH_LAYOUT_DEFAULT_NODESEP,
      ranksep: GRAPH_LAYOUT_DEFAULT_RANKSEP,
    })
  })

  it('buildG6FitViewPadding leaves compact bottom inset for floating legend', () => {
    expect(buildG6FitViewPadding({ compact: true })).toEqual([24, 24, 100, 24])
    expect(buildG6FitViewPadding({ compact: false })).toBe(32)
  })
})

describe('graph node label contrast + edge label chrome (D)', () => {
  it('keeps type stroke on nodes while fill uses surface layer for canvas separation', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const payload = buildG6GraphData(graph)
    const lensNode = payload.nodes.find((node) => node.id === 'n_lens')

    expect(lensNode?.data.strokeColor).toBe(getGraphNodeTypeColor('AnalyticalLens', 'HSS'))
    expect(lensNode?.data.fill).toBe(GRAPH_NODE_SURFACE_FILL)
    expect(lensNode?.data.fill).not.toBe(lensNode?.data.strokeColor)
  })

  it('buildG6NodeStyleOptions binds primary labelFill token for readable node text', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const options = buildG6NodeStyleOptions(theme, () => '核心论点\n(Thesis)')

    expect(options.style.labelFill).toBe(theme.labelFill)
    expect(options.style.labelFill).toBe('#111827')
    expect(options.style.fill({ data: { fill: getGraphNodeFillColor('Thesis', 'HSS') } })).toBe(
      getGraphNodeFillColor('Thesis', 'HSS'),
    )
  })

  it('buildG6EdgeStyleOptions wires centered caption labels with surface background padding', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const edgeOptions = buildG6EdgeStyleOptions(theme)

    expect(edgeOptions.style.labelPlacement).toBe('center')
    expect(edgeOptions.style.labelBackground).toBe(true)
    expect(edgeOptions.style.labelBackgroundFill).toBe(theme.edgeLabelBackground)
    expect(edgeOptions.style.labelPadding).toEqual([2, 4, 2, 4])
    expect(edgeOptions.style.labelFill).toBe(theme.edgeLabelFill)
    expect(edgeOptions.style.labelAutoRotate).toBe(false)
  })

  it('buildG6Behaviors + node animation avoid hover displacement (stroke-only motion budget)', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const nodeOptions = buildG6NodeStyleOptions(theme, () => 'label')
    const hoverBehavior = buildG6Behaviors().find((item) => typeof item === 'object' && item.type === 'hover-activate')

    expect(hoverBehavior).toMatchObject({ type: 'hover-activate', state: 'hover' })
    expect(nodeOptions.state.hover).toEqual({ stroke: theme.hoverStroke, lineWidth: 2 })
    expect(nodeOptions.animation.update[0].fields).toEqual(['stroke', 'lineWidth', 'fill'])
    expect(nodeOptions.animation.update[0].fields).not.toContain('x')
    expect(nodeOptions.animation.update[0].fields).not.toContain('y')
    expect(GRAPH_NODE_FILL_TINT_RATIO).toBeGreaterThan(0)
  })
})

describe('§17 graph viewport size constants', () => {
  it('maps Detail compact design reference to GRAPH_COMPACT_HEIGHT = 320', () => {
    expect(GRAPH_COMPACT_HEIGHT).toBe(320)
  })

  it('maps Graph default viewport to GRAPH_DEFAULT_HEIGHT = 480 with 720px full-bleed floor', () => {
    expect(GRAPH_DEFAULT_HEIGHT).toBe(480)
    expect(GRAPH_FULL_MIN_HEIGHT).toBe(720)
    expect(GRAPH_FULL_MIN_HEIGHT).toBeGreaterThan(GRAPH_DEFAULT_HEIGHT)
  })
})

describe('graph node lookup helpers', () => {
  const graph = graphFixture.data as UnifiedPaperGraph

  it('findGraphNodeById returns node for drawer and deep-link selection', () => {
    const node = findGraphNodeById(graph, 'n_lens')
    expect(node?.label).toBe('历史制度主义')
    expect(findGraphNodeById(graph, 'missing')).toBeUndefined()
  })

  it('getGraphNodeSnippet reads trimmed snippet from node.data', () => {
    const withSnippet = findGraphNodeById(graph, 'n1')
    expect(getGraphNodeSnippet(withSnippet)).toBeNull()

    expect(getGraphNodeSnippet({ id: 'n9', label: 'x', type: 'Thesis', data: { snippet: '  摘录  ' } })).toBe('摘录')
    expect(getGraphNodeSnippet({ id: 'n9', label: 'x', type: 'Thesis', data: { snippet: '   ' } })).toBeNull()
  })
})
