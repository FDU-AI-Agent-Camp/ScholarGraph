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

  it('detects classifier heuristic fallback code', () => {
    expect(hasClassifierHeuristicFallback([CLASSIFIER_HEURISTIC_FALLBACK_CODE])).toBe(true)
    expect(hasClassifierHeuristicFallback([])).toBe(false)
  })
})
