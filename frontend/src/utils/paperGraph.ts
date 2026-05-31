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
