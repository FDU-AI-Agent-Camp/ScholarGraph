import { describe, expect, it } from 'vitest'

import {
  CLASSIFIER_HEURISTIC_FALLBACK_CODE,
  CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
  hasClassifierHeuristicFallback,
  resolveClassifyWarningMessages,
} from '@/utils/classifyWarnings'

describe('classifyWarnings', () => {
  it('maps classifier_heuristic_fallback to frozen user message', () => {
    expect(resolveClassifyWarningMessages([CLASSIFIER_HEURISTIC_FALLBACK_CODE])).toEqual([
      CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('returns empty list when codes are absent', () => {
    expect(resolveClassifyWarningMessages([])).toEqual([])
    expect(resolveClassifyWarningMessages(undefined)).toEqual([])
    expect(resolveClassifyWarningMessages(null)).toEqual([])
  })

  it('detects heuristic fallback code', () => {
    expect(hasClassifierHeuristicFallback([CLASSIFIER_HEURISTIC_FALLBACK_CODE])).toBe(true)
    expect(hasClassifierHeuristicFallback([])).toBe(false)
    expect(hasClassifierHeuristicFallback(undefined)).toBe(false)
    expect(hasClassifierHeuristicFallback(null)).toBe(false)
  })

  it('does not show warning UI when only unknown codes are present', () => {
    expect(resolveClassifyWarningMessages(['other_code'])).toEqual(['other_code'])
    expect(hasClassifierHeuristicFallback(['other_code'])).toBe(false)
  })

  it('deduplicates repeated machine codes in display messages', () => {
    expect(
      resolveClassifyWarningMessages([CLASSIFIER_HEURISTIC_FALLBACK_CODE, CLASSIFIER_HEURISTIC_FALLBACK_CODE]),
    ).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE])
  })

  it('frozen message matches progress.md copy exactly', () => {
    expect(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE).toBe('触发分类启发式Fallback!')
  })

  it('maps known code and passes unknown codes in mixed lists', () => {
    expect(resolveClassifyWarningMessages([CLASSIFIER_HEURISTIC_FALLBACK_CODE, 'future_code'])).toEqual([
      CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
      'future_code',
    ])
  })
})
