import type { QaStreamCitationData } from '@/api/types'

export type QaStreamNodeCitation = Extract<QaStreamCitationData, { type: 'node' }>

export { appendUniqueCitation, citationDisplayId, citationKey } from './paperGraph'

/** Test/Mock helper — V2 node citation shape. */
export function nodeCitation(paper_id: string, node_id: string, label: string): QaStreamNodeCitation {
  return { type: 'node', paper_id, node_id, label }
}

export function isNodeCitation(citation: QaStreamCitationData): citation is QaStreamNodeCitation {
  return citation.type === 'node'
}

export function citationNodeId(citation: QaStreamCitationData): string | null {
  return citation.type === 'node' ? citation.node_id : null
}
