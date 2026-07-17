/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** Phase F.2.3 — machine codes → user-visible extract degrade messages. */

export const EXTRACT_HEURISTIC_FALLBACK_CODE = 'extract_heuristic_fallback' as const

/** Frozen user-visible copy (progress.md §F.2.3 / backend extract_constants). */
export const EXTRACT_HEURISTIC_FALLBACK_MESSAGE = '触发启发式Fallback!' as const

/** MVP skeleton preview while deep nodes assemble in the background. */
export const MVP_SKELETON_PREVIEW_CODE = 'mvp_skeleton_preview' as const

export const MVP_SKELETON_PREVIEW_MESSAGE = '当前为 MVP 宏观骨架图谱，深度节点仍在后台组装中。' as const

export const EXTRACT_LLM_TIMEOUT_CODE = 'extract_llm_timeout' as const

export const EXTRACT_LLM_TIMEOUT_MESSAGE = 'LLM 调用超时，已降级为启发式Fallback。' as const

export const EXTRACT_LLM_RATE_LIMITED_CODE = 'extract_llm_rate_limited' as const

export const EXTRACT_LLM_RATE_LIMITED_MESSAGE = 'LLM 触发限流，已降级为启发式Fallback。' as const

export const EXTRACT_LLM_JSON_INVALID_CODE = 'extract_llm_json_invalid' as const

export const EXTRACT_LLM_JSON_INVALID_MESSAGE = 'LLM 返回非合法 JSON，已降级为启发式Fallback。' as const

export const EXTRACT_SCHEMA_VALIDATION_FAILED_CODE = 'extract_schema_validation_failed' as const

export const EXTRACT_SCHEMA_VALIDATION_FAILED_MESSAGE = 'Schema 校验失败，已降级为启发式Fallback。' as const

export const EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE = 'extract_context_window_exceeded' as const

export const EXTRACT_CONTEXT_WINDOW_EXCEEDED_MESSAGE = '上下文窗口超限，已降级为启发式Fallback。' as const

export const LOW_CONFIDENCE_GRAPH_CODE = 'low_confidence_graph' as const

export const LOW_CONFIDENCE_GRAPH_MESSAGE = '图谱质量未达置信门控，建议人工复核或重新抽取。' as const

/** P13 micro wait_for — RAG index timed out; paper remains interactive. */
export const RAG_INDEX_TIMEOUT_CODE = 'rag_index_timeout' as const

export const RAG_INDEX_TIMEOUT_MESSAGE =
  '向量索引处理超时，全量图谱与问答功能已就绪，但深度文本证据链可能不完整。' as const

/** P13 macro out-of-loop watchdog — stuck indexing healed. */
export const RAG_INDEXING_STUCK_TIMEOUT_CODE = 'rag_indexing_stuck_timeout' as const

export const RAG_INDEXING_STUCK_TIMEOUT_MESSAGE =
  '系统已自动终止卡死的索引调度。图谱与基础问答仍可交互，部分原文引用证据正在自愈刷新中。' as const

/** UX-W1 — never leak unknown machine codes into primary UI copy. */
export const EXTRACT_WARNING_UNKNOWN_MESSAGE = '建图已完成，检测到局部算法指标偏离，正在以兼容模式运行。' as const

const EXTRACT_WARNING_MESSAGES: Readonly<Record<string, string>> = {
  [EXTRACT_HEURISTIC_FALLBACK_CODE]: EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
  [MVP_SKELETON_PREVIEW_CODE]: MVP_SKELETON_PREVIEW_MESSAGE,
  [EXTRACT_LLM_TIMEOUT_CODE]: EXTRACT_LLM_TIMEOUT_MESSAGE,
  [EXTRACT_LLM_RATE_LIMITED_CODE]: EXTRACT_LLM_RATE_LIMITED_MESSAGE,
  [EXTRACT_LLM_JSON_INVALID_CODE]: EXTRACT_LLM_JSON_INVALID_MESSAGE,
  [EXTRACT_SCHEMA_VALIDATION_FAILED_CODE]: EXTRACT_SCHEMA_VALIDATION_FAILED_MESSAGE,
  [EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE]: EXTRACT_CONTEXT_WINDOW_EXCEEDED_MESSAGE,
  [LOW_CONFIDENCE_GRAPH_CODE]: LOW_CONFIDENCE_GRAPH_MESSAGE,
  [RAG_INDEX_TIMEOUT_CODE]: RAG_INDEX_TIMEOUT_MESSAGE,
  [RAG_INDEXING_STUCK_TIMEOUT_CODE]: RAG_INDEXING_STUCK_TIMEOUT_MESSAGE,
}

export interface ExtractWarningDisplay {
  /** User-facing Chinese copy (never a raw machine code). */
  message: string
  /** Present only for unregistered codes — for title tooltip / secondary UI. */
  technicalCode?: string
}

/**
 * Resolve extract_warnings codes to display entries.
 * Unknown codes collapse to a single friendly fallback; machine code is optional metadata.
 */
export function resolveExtractWarningDisplays(codes: string[] | undefined | null): ExtractWarningDisplay[] {
  if (!codes?.length) {
    return []
  }

  const displays: ExtractWarningDisplay[] = []
  const seenMessages = new Set<string>()
  const unknownTechnicalCodes: string[] = []

  for (const code of codes) {
    const registered = EXTRACT_WARNING_MESSAGES[code]
    if (registered) {
      if (!seenMessages.has(registered)) {
        seenMessages.add(registered)
        displays.push({ message: registered })
      }
      continue
    }
    unknownTechnicalCodes.push(code)
  }

  if (unknownTechnicalCodes.length) {
    if (!seenMessages.has(EXTRACT_WARNING_UNKNOWN_MESSAGE)) {
      seenMessages.add(EXTRACT_WARNING_UNKNOWN_MESSAGE)
      displays.push({
        message: EXTRACT_WARNING_UNKNOWN_MESSAGE,
        technicalCode: [...new Set(unknownTechnicalCodes)].join(', '),
      })
    }
  }

  return displays
}

/** Map API warning codes to display strings; unknown codes use graceful Chinese fallback. */
export function resolveExtractWarningMessages(codes: string[] | undefined | null): string[] {
  return resolveExtractWarningDisplays(codes).map((entry) => entry.message)
}

export function hasExtractHeuristicFallback(codes: string[] | undefined | null): boolean {
  return Boolean(codes?.includes(EXTRACT_HEURISTIC_FALLBACK_CODE))
}
