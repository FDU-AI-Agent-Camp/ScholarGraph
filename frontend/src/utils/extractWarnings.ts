/** Phase F.2.3 — machine codes → user-visible extract degrade messages. */

export const EXTRACT_HEURISTIC_FALLBACK_CODE = 'extract_heuristic_fallback' as const

/** Frozen user-visible copy (progress.md §F.2.3). */
export const EXTRACT_HEURISTIC_FALLBACK_MESSAGE = '触发启发式Fallback!' as const

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
