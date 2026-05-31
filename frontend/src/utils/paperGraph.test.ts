import { describe, expect, it } from 'vitest'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import type { UnifiedPaperGraph } from '@/api/types'

import {
  buildG6EdgeStyleOptions,
  buildG6GraphData,
  buildG6NodeStyleOptions,
  buildHighlightStateMap,
  citationKey,
  estimateGraphNodeSize,
  findGraphNodeById,
  getGraphNodeSnippet,
  getGraphNodeTypeColor,
  listGraphLegendEntries,
  resolvePaperGraphThemeTokens,
  toG6GraphPayload,
  GRAPH_EDGE_STROKE,
  GRAPH_COMPACT_HEIGHT,
  GRAPH_DEFAULT_HEIGHT,
  GRAPH_FULL_MIN_HEIGHT,
  GRAPH_NODE_MIN_WIDTH,
  GRAPH_NODE_MAX_WIDTH,
} from './paperGraph'

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

  it('buildG6GraphData attaches paradigm fill and clamped size to each node', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const payload = buildG6GraphData(graph)
    const thesis = payload.nodes.find((node) => node.id === 'n1')

    expect(thesis?.data.fill).toBe(getGraphNodeTypeColor('Thesis', 'HSS'))
    expect(Array.isArray(thesis?.data.size)).toBe(true)
    const [width, height] = thesis?.data.size as [number, number]
    expect(width).toBeGreaterThanOrEqual(GRAPH_NODE_MIN_WIDTH)
    expect(width).toBeLessThanOrEqual(GRAPH_NODE_MAX_WIDTH)
    expect(height).toBeGreaterThanOrEqual(40)
  })

  it('buildG6EdgeStyleOptions uses design-spec edge stroke color', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const edgeOptions = buildG6EdgeStyleOptions(theme)

    expect(edgeOptions.style.stroke).toBe(GRAPH_EDGE_STROKE)
    expect(edgeOptions.style.lineWidth).toBe(1)
    expect(edgeOptions.style.endArrow).toBe(true)
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
