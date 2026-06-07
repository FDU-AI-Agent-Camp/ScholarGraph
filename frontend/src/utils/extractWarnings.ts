/** Phase F.2.3 — machine codes → user-visible extract degrade messages. */

export const EXTRACT_HEURISTIC_FALLBACK_CODE = 'extract_heuristic_fallback' as const

/** Frozen user-visible copy (progress.md §F.2.3). */
export const EXTRACT_HEURISTIC_FALLBACK_MESSAGE = '触发启发式Fallback!' as const

const EXTRACT_WARNING_MESSAGES: Readonly<Record<string, string>> = {
  [EXTRACT_HEURISTIC_FALLBACK_CODE]: EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
}

/** Map API warning codes to display strings; unknown codes pass through. */
export function resolveExtractWarningMessages(codes: string[] | undefined | null): string[] {
  if (!codes?.length) {
    return []
  }
  const messages = codes.map((code) => EXTRACT_WARNING_MESSAGES[code] ?? code)
  return [...new Set(messages)]
}

export function hasExtractHeuristicFallback(codes: string[] | undefined | null): boolean {
  return Boolean(codes?.includes(EXTRACT_HEURISTIC_FALLBACK_CODE))
}
