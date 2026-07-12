import type { QaStreamCitationData } from '@/api/types'

export type QaStreamNodeCitation = Extract<QaStreamCitationData, { type: 'node' }>
export type QaStreamChunkCitation = Extract<QaStreamCitationData, { type: 'chunk' }>

export { appendUniqueCitation, citationDisplayId, citationKey } from './paperGraph'

/** OpenAPI `ChunkPreviewState` — keep aligned with backend/schemas/chunk_preview.py */
export type ChunkPreviewState =
  | 'ready'
  | 'indexing'
  | 'retrieval_timeout'
  | 'l2_timeout'
  | 'hallucinated_id'

export const CHUNK_PREVIEW_DEGRADED_STATES: ReadonlySet<ChunkPreviewState> = new Set([
  'indexing',
  'retrieval_timeout',
  'l2_timeout',
  'hallucinated_id',
])

export function isChunkPreviewDegraded(state: ChunkPreviewState): boolean {
  return CHUNK_PREVIEW_DEGRADED_STATES.has(state)
}

export function chunkPreviewPlaceholderTooltip(state: ChunkPreviewState): string | undefined {
  if (!isChunkPreviewDegraded(state)) {
    return undefined
  }
  switch (state) {
    case 'indexing':
      return '原文向量索引尚未完成，请稍后刷新页面再试。'
    case 'retrieval_timeout':
    case 'l2_timeout':
      return '向量检索超时，当前仅依据图谱作答，原文预览暂不可用。'
    case 'hallucinated_id':
      return '模型引用了无法验证的片段 ID，请谨慎采纳。'
    default: {
      const _exhaustive: never = state
      return _exhaustive
    }
  }
}

/** Test/Mock helper — V2 node citation shape. */
export function nodeCitation(paper_id: string, node_id: string, label: string): QaStreamNodeCitation {
  return { type: 'node', paper_id, node_id, label }
}

export function isNodeCitation(citation: QaStreamCitationData): citation is QaStreamNodeCitation {
  return citation.type === 'node'
}

export function isChunkCitation(citation: QaStreamCitationData): citation is QaStreamChunkCitation {
  return citation.type === 'chunk'
}

export function citationNodeId(citation: QaStreamCitationData): string | null {
  return citation.type === 'node' ? citation.node_id : null
}

export function chunkCitationPreview(citation: QaStreamCitationData): string | null {
  return citation.type === 'chunk' ? citation.text_preview : null
}

export function chunkCitationPreviewState(citation: QaStreamCitationData): ChunkPreviewState | null {
  return citation.type === 'chunk' ? citation.preview_state : null
}
