/** Phase G — machine codes → user-visible classify degrade messages. */

export const CLASSIFIER_HEURISTIC_FALLBACK_CODE = 'classifier_heuristic_fallback' as const

/** Frozen user-visible copy (progress.md §G.2). */
export const CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE = '触发分类启发式Fallback!' as const

const CLASSIFY_WARNING_MESSAGES: Readonly<Record<string, string>> = {
  [CLASSIFIER_HEURISTIC_FALLBACK_CODE]: CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
}

/** Map API warning codes to display strings; unknown codes pass through. */
export function resolveClassifyWarningMessages(codes: string[] | undefined | null): string[] {
  if (!codes?.length) {
    return []
  }
  const messages = codes.map((code) => CLASSIFY_WARNING_MESSAGES[code] ?? code)
  return [...new Set(messages)]
}

export function hasClassifierHeuristicFallback(codes: string[] | undefined | null): boolean {
  return Boolean(codes?.includes(CLASSIFIER_HEURISTIC_FALLBACK_CODE))
}
