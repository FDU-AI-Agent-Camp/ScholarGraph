import { describe, expect, it } from 'vitest'

import {
  EXTRACT_HEURISTIC_FALLBACK_CODE,
  EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
  hasExtractHeuristicFallback,
  resolveExtractWarningMessages,
} from '@/utils/extractWarnings'

describe('extractWarnings', () => {
  it('maps extract_heuristic_fallback to frozen user message', () => {
    expect(resolveExtractWarningMessages([EXTRACT_HEURISTIC_FALLBACK_CODE])).toEqual([
      EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('returns empty list when codes are absent', () => {
    expect(resolveExtractWarningMessages([])).toEqual([])
    expect(resolveExtractWarningMessages(undefined)).toEqual([])
  })

  it('detects heuristic fallback code', () => {
    expect(hasExtractHeuristicFallback([EXTRACT_HEURISTIC_FALLBACK_CODE])).toBe(true)
    expect(hasExtractHeuristicFallback([])).toBe(false)
  })

  it('does not show warning UI when only unknown codes are present', () => {
    expect(resolveExtractWarningMessages(['other_code'])).toEqual(['other_code'])
    expect(hasExtractHeuristicFallback(['other_code'])).toBe(false)
  })

  it('deduplicates repeated machine codes in display messages', () => {
    expect(resolveExtractWarningMessages([EXTRACT_HEURISTIC_FALLBACK_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE])).toEqual([
      EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('frozen message matches progress.md copy exactly', () => {
    expect(EXTRACT_HEURISTIC_FALLBACK_MESSAGE).toBe('触发启发式Fallback!')
  })
})
