import type { Paradigm, UnifiedPaperGraph } from '@/api/types'
import type { QaStreamCitationData } from '@/api/types'

/** G6 node/edge payload derived from API graph (testable without canvas). */
export interface G6GraphPayload {
  nodes: Array<{ id: string; data: Record<string, unknown> }>
  edges: Array<{ id: string; source: string; target: string; data: Record<string, unknown> }>
}

export interface GraphLegendEntry {
  type: string
  label: string
  color: string
}

const HSS_NODE_TYPE_COLORS: Record<string, string> = {
  Intellectual_Context: '#78716c',
  Thesis: '#0d6e6e',
  Sub_argument: '#0891b2',
  SubArgument: '#0891b2',
  Analytical_Lens: '#7c3aed',
  AnalyticalLens: '#7c3aed',
  Object_or_Data: '#ca8a04',
  ObjectOrData: '#ca8a04',
}

const STEM_NODE_TYPE_COLORS: Record<string, string> = {
  Research_Question: '#0d6e6e',
  ResearchQuestion: '#0d6e6e',
  Method: '#2563eb',
  Dataset: '#0891b2',
  Metric: '#059669',
  Claim: '#d97706',
  Evidence: '#64748b',
}

const DEFAULT_NODE_TYPE_COLOR = '#0d6e6e'

/** design-spec §10 / §17 graph layout constants (testable without canvas). */
export const GRAPH_NODE_MIN_WIDTH = 80
export const GRAPH_NODE_MAX_WIDTH = 140
export const GRAPH_NODE_MIN_HEIGHT = 40
export const GRAPH_NODE_RADIUS = 8
export const GRAPH_NODE_LABEL_FONT_SIZE = 12
export const GRAPH_EDGE_STROKE = '#94a3b8'
export const GRAPH_COMPACT_HEIGHT = 320
export const GRAPH_DEFAULT_HEIGHT = 480
export const GRAPH_FULL_MIN_HEIGHT = 720
export const GRAPH_STATE_ANIMATION_MS = 120
export const GRAPH_HOVER_LINE_WIDTH = 2
export const GRAPH_ACTIVE_LINE_WIDTH = 3
export const GRAPH_ZOOM_STEP = 1.2

export interface PaperGraphThemeTokens {
  defaultStroke: string
  hoverStroke: string
  activeFill: string
  activeStroke: string
  edgeStroke: string
}

export function resolvePaperGraphThemeTokens(
  readToken: (name: string, fallback: string) => string,
): PaperGraphThemeTokens {
  return {
    defaultStroke: readToken('--color-primary-hover', '#0a5858'),
    hoverStroke: readToken('--color-primary', '#0d6e6e'),
    activeFill: readToken('--color-citation-active-bg', '#fff1f2'),
    activeStroke: readToken('--color-citation-active', '#e11d48'),
    edgeStroke: GRAPH_EDGE_STROKE,
  }
}

export function estimateGraphNodeSize(label: string, nodeType?: string): [number, number] {
  const typeSuffix = nodeType ? `\n(${nodeType})` : ''
  const text = `${label}${typeSuffix}`
  const width = Math.min(GRAPH_NODE_MAX_WIDTH, Math.max(GRAPH_NODE_MIN_WIDTH, Math.ceil(text.length * 6.5) + 24))
  return [width, GRAPH_NODE_MIN_HEIGHT]
}

export function buildG6GraphData(graph: UnifiedPaperGraph): G6GraphPayload {
  const payload = toG6GraphPayload(graph)
  return {
    ...payload,
    nodes: payload.nodes.map((node) => {
      const nodeType = String(node.data.nodeType ?? '')
      const label = String(node.data.label ?? '')
      const [width, height] = estimateGraphNodeSize(label, nodeType)
      return {
        ...node,
        data: {
          ...node.data,
          fill: getGraphNodeTypeColor(nodeType, graph.paradigm),
          size: [width, height],
        },
      }
    }),
  }
}

export function buildG6NodeStyleOptions(
  theme: PaperGraphThemeTokens,
  labelText: (datum: { data?: { label?: string; nodeType?: string } }) => string,
) {
  return {
    type: 'rect' as const,
    style: {
      radius: GRAPH_NODE_RADIUS,
      labelText,
      labelFontSize: GRAPH_NODE_LABEL_FONT_SIZE,
      labelPlacement: 'center' as const,
      labelWordWrap: true,
      labelMaxLines: 2,
      labelMaxWidth: GRAPH_NODE_MAX_WIDTH - 16,
      fill: (datum: { data?: { fill?: string } }) => datum.data?.fill ?? DEFAULT_NODE_TYPE_COLOR,
      size: (datum: { data?: { size?: [number, number] } }) =>
        datum.data?.size ?? [GRAPH_NODE_MIN_WIDTH, GRAPH_NODE_MIN_HEIGHT],
      stroke: theme.defaultStroke,
      lineWidth: 1,
    },
    state: {
      hover: {
        stroke: theme.hoverStroke,
        lineWidth: GRAPH_HOVER_LINE_WIDTH,
      },
      active: {
        fill: theme.activeFill,
        stroke: theme.activeStroke,
        lineWidth: GRAPH_ACTIVE_LINE_WIDTH,
      },
    },
    animation: {
      update: [
        {
          fields: ['stroke', 'lineWidth', 'fill'],
          duration: GRAPH_STATE_ANIMATION_MS,
        },
      ],
    },
  }
}

export function buildG6EdgeStyleOptions(theme: PaperGraphThemeTokens) {
  return {
    style: {
      stroke: theme.edgeStroke,
      lineWidth: 1,
      labelFontSize: 10,
      labelText: (datum: { data?: { label?: string } }) => datum.data?.label ?? '',
      endArrow: true,
    },
  }
}

type G6BehaviorOption =
  | 'drag-canvas'
  | 'zoom-canvas'
  | 'drag-element'
  | 'click-select'
  | {
      type: 'hover-activate'
      state: 'hover'
      animation: boolean
    }

export function buildG6Behaviors(): G6BehaviorOption[] {
  return [
    'drag-canvas',
    'zoom-canvas',
    'drag-element',
    'click-select',
    {
      type: 'hover-activate',
      state: 'hover',
      animation: true,
    },
  ]
}

export function getGraphNodeTypeColor(nodeType: string, paradigm?: Paradigm | null): string {
  const palette = paradigm === 'STEM' ? STEM_NODE_TYPE_COLORS : HSS_NODE_TYPE_COLORS
  return palette[nodeType] ?? DEFAULT_NODE_TYPE_COLOR
}

/** Unique node types for compact graph legend (design-spec §9.7.3). */
export function listGraphLegendEntries(graph: UnifiedPaperGraph): GraphLegendEntry[] {
  const seen = new Set<string>()
  const entries: GraphLegendEntry[] = []

  for (const node of graph.nodes) {
    if (seen.has(node.type)) {
      continue
    }
    seen.add(node.type)
    entries.push({
      type: node.type,
      label: node.type,
      color: getGraphNodeTypeColor(node.type, graph.paradigm),
    })
  }

  return entries
}

export function toG6GraphPayload(graph: UnifiedPaperGraph): G6GraphPayload {
  return {
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      data: {
        label: node.label,
        nodeType: node.type,
        ...(node.data ?? {}),
      },
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      data: {
        label: edge.label,
        edgeType: edge.type,
      },
    })),
  }
}

/** Map node ids to G6 `active` state for citation highlight. */
export function buildHighlightStateMap(
  nodeIds: string[],
  highlightNodeId: string | null | undefined,
): Record<string, 'active' | []> {
  const states: Record<string, 'active' | []> = {}
  for (const nodeId of nodeIds) {
    states[nodeId] = nodeId === highlightNodeId ? 'active' : []
  }
  return states
}

export function appendUniqueCitation(
  citations: QaStreamCitationData[],
  incoming: QaStreamCitationData,
): QaStreamCitationData[] {
  if (citations.some((item) => item.node_id === incoming.node_id && item.paper_id === incoming.paper_id)) {
    return citations
  }
  return [...citations, incoming]
}

export function citationKey(citation: QaStreamCitationData): string {
  return `${citation.paper_id}:${citation.node_id}`
}
