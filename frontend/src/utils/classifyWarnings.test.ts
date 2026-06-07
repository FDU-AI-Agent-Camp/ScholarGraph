import { describe, expect, it } from 'vitest'

import {
  CLASSIFIER_HEURISTIC_FALLBACK_CODE,
  CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
  hasClassifierHeuristicFallback,
  resolveClassifyWarningMessages,
} from '@/utils/classifyWarnings'

const FROZEN_CODE = 'classifier_heuristic_fallback'
const FROZEN_MESSAGE = '触发分类启发式Fallback!'

describe('classifyWarnings', () => {
  it('freezes machine code constant', () => {
    expect(CLASSIFIER_HEURISTIC_FALLBACK_CODE).toBe(FROZEN_CODE)
  })

  it('freezes user-visible message constant', () => {
    expect(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE).toBe(FROZEN_MESSAGE)
  })

  it('maps classifier_heuristic_fallback to frozen user message', () => {
    expect(resolveClassifyWarningMessages([CLASSIFIER_HEURISTIC_FALLBACK_CODE])).toEqual([
      CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('detects classifier heuristic fallback code', () => {
    expect(hasClassifierHeuristicFallback([CLASSIFIER_HEURISTIC_FALLBACK_CODE])).toBe(true)
    expect(hasClassifierHeuristicFallback([])).toBe(false)
    expect(hasClassifierHeuristicFallback(undefined)).toBe(false)
    expect(hasClassifierHeuristicFallback(null)).toBe(false)
  })

  it('passes through unknown codes unchanged', () => {
    expect(resolveClassifyWarningMessages(['future_code'])).toEqual(['future_code'])
  })

  it('deduplicates resolved messages', () => {
    expect(
      resolveClassifyWarningMessages([
        CLASSIFIER_HEURISTIC_FALLBACK_CODE,
        CLASSIFIER_HEURISTIC_FALLBACK_CODE,
      ]),
    ).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE])
  })

  it('maps known code and passes unknown codes in mixed lists', () => {
    expect(
      resolveClassifyWarningMessages([CLASSIFIER_HEURISTIC_FALLBACK_CODE, 'future_code']),
    ).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE, 'future_code'])
  })

  it('returns empty array for empty or missing input', () => {
    expect(resolveClassifyWarningMessages([])).toEqual([])
    expect(resolveClassifyWarningMessages(undefined)).toEqual([])
    expect(resolveClassifyWarningMessages(null)).toEqual([])
  })
})
