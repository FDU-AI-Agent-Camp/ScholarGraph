/** QA-D1 — map SSE warning codes to bubble-level Chinese copy. */

export const RAG_INDEX_NOT_READY_CODE = 'RAG_INDEX_NOT_READY' as const

export const RAG_INDEX_NOT_READY_MESSAGE =
  '当前原文向量索引未就绪，本次检索已安全退化为「纯图谱子图」推理。回答已最大程度生成，但暂无法提供精确的页码与高亮文本块引用。' as const

const VECTOR_RETRIEVAL_TIMEOUT_CODE = 'vector_retrieval_timeout'
const VECTOR_STORE_UNAVAILABLE_CODE = 'vector_store_unavailable'

const QA_STREAM_WARNING_MESSAGES: Readonly<Record<string, string>> = {
  [RAG_INDEX_NOT_READY_CODE]: RAG_INDEX_NOT_READY_MESSAGE,
  [VECTOR_RETRIEVAL_TIMEOUT_CODE]: '向量检索超时，正在使用纯图知识库答题。',
  [VECTOR_STORE_UNAVAILABLE_CODE]: '向量库连接异常，已自动降级为纯图谱检索模式。',
}

export interface QaStreamWarningData {
  code?: string
  message: string
  source?: string
}

/** Prefer registered Chinese copy; fall back to server message. */
export function resolveQaStreamWarningMessage(warning: QaStreamWarningData): string {
  const code = warning.code?.trim()
  if (code && QA_STREAM_WARNING_MESSAGES[code]) {
    return QA_STREAM_WARNING_MESSAGES[code]
  }
  const serverMessage = warning.message.trim()
  return serverMessage || '本次检索已降级，回答可能缺少原文引用证据。'
}
