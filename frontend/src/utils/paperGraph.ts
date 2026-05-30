import type { UnifiedPaperGraph } from '@/api/types'
import type { QaStreamCitationData } from '@/api/types'

/** G6 node/edge payload derived from API graph (testable without canvas). */
export interface G6GraphPayload {
  nodes: Array<{ id: string; data: Record<string, unknown> }>
  edges: Array<{ id: string; source: string; target: string; data: Record<string, unknown> }>
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
