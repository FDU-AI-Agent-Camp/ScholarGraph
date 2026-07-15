import { describe, expect, it } from 'vitest'

import {
  EXTRACT_HEURISTIC_FALLBACK_CODE,
  EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
  EXTRACT_WARNING_UNKNOWN_MESSAGE,
  RAG_INDEXING_STUCK_TIMEOUT_CODE,
  RAG_INDEXING_STUCK_TIMEOUT_MESSAGE,
  RAG_INDEX_TIMEOUT_CODE,
  RAG_INDEX_TIMEOUT_MESSAGE,
  hasExtractHeuristicFallback,
  resolveExtractWarningDisplays,
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

  it('maps rag_index_timeout to user-visible index timeout copy (G1 / P13)', () => {
    expect(resolveExtractWarningMessages([RAG_INDEX_TIMEOUT_CODE])).toEqual([RAG_INDEX_TIMEOUT_MESSAGE])
  })

  it.each([
    {
      name: 'rag_indexing_stuck_timeout (UX-W1 watchdog)',
      code: RAG_INDEXING_STUCK_TIMEOUT_CODE,
      expected: RAG_INDEXING_STUCK_TIMEOUT_MESSAGE,
      mustInclude: '自动终止卡死',
    },
    {
      name: 'rag_index_timeout (micro wait_for)',
      code: RAG_INDEX_TIMEOUT_CODE,
      expected: RAG_INDEX_TIMEOUT_MESSAGE,
      mustInclude: '向量索引',
    },
  ])('maps $name without leaking machine code', ({ code, expected, mustInclude }) => {
    const messages = resolveExtractWarningMessages([code])
    expect(messages).toEqual([expected])
    expect(messages[0]).toContain(mustInclude)
    expect(messages[0]).not.toBe(code)
    expect(messages[0]).not.toContain('_')
  })

  it('never returns raw unknown machine codes — graceful Chinese fallback (UX-W1)', () => {
    const messages = resolveExtractWarningMessages(['other_code', 'quality_gate_xyz'])
    expect(messages).toHaveLength(1)
    expect(messages[0]).toBe(EXTRACT_WARNING_UNKNOWN_MESSAGE)
    expect(messages[0]).not.toContain('other_code')
    expect(messages[0]).not.toContain('_')
  })

  it('attaches technicalCode on unknown displays for title / secondary UI', () => {
    const displays = resolveExtractWarningDisplays(['mystery_warn'])
    expect(displays).toEqual([
      {
        message: EXTRACT_WARNING_UNKNOWN_MESSAGE,
        technicalCode: 'mystery_warn',
      },
    ])
  })

  it('omits technicalCode for registered codes', () => {
    expect(resolveExtractWarningDisplays([RAG_INDEXING_STUCK_TIMEOUT_CODE])).toEqual([
      { message: RAG_INDEXING_STUCK_TIMEOUT_MESSAGE },
    ])
  })

  it('deduplicates repeated machine codes in display messages', () => {
    expect(resolveExtractWarningMessages([EXTRACT_HEURISTIC_FALLBACK_CODE, EXTRACT_HEURISTIC_FALLBACK_CODE])).toEqual([
      EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('deduplicates multiple unknown codes into one fallback banner', () => {
    expect(resolveExtractWarningMessages(['a_unknown', 'b_unknown'])).toEqual([EXTRACT_WARNING_UNKNOWN_MESSAGE])
  })

  it('frozen heuristic message matches progress.md copy exactly', () => {
    expect(EXTRACT_HEURISTIC_FALLBACK_MESSAGE).toBe('触发启发式Fallback!')
  })
})
