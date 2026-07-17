/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE,
  EXTRACT_HEURISTIC_FALLBACK_CODE,
  EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
  EXTRACT_LLM_JSON_INVALID_CODE,
  EXTRACT_LLM_RATE_LIMITED_CODE,
  EXTRACT_LLM_TIMEOUT_CODE,
  EXTRACT_SCHEMA_VALIDATION_FAILED_CODE,
  EXTRACT_WARNING_UNKNOWN_MESSAGE,
  LOW_CONFIDENCE_GRAPH_CODE,
  MVP_SKELETON_PREVIEW_CODE,
  MVP_SKELETON_PREVIEW_MESSAGE,
  RAG_INDEXING_STUCK_TIMEOUT_CODE,
  RAG_INDEXING_STUCK_TIMEOUT_MESSAGE,
  RAG_INDEX_TIMEOUT_CODE,
  RAG_INDEX_TIMEOUT_MESSAGE,
  hasExtractHeuristicFallback,
  resolveExtractWarningDisplays,
  resolveExtractWarningMessages,
} from '@/utils/extractWarnings'

const REPO_ROOT = resolve(__dirname, '../../..')
const EXTRACT_CONSTANTS_PY = resolve(REPO_ROOT, 'backend/agents/extract_constants.py')

function loadBackendExtractWarningCatalog(): Array<{ code: string; message: string }> {
  const text = readFileSync(EXTRACT_CONSTANTS_PY, 'utf8')
  const codes = new Map<string, string>()
  const messages = new Map<string, string>()
  for (const match of text.matchAll(/^([A-Z0-9_]+_CODE)\s*=\s*"([^"]+)"/gm)) {
    codes.set(match[1], match[2])
  }
  for (const match of text.matchAll(/^([A-Z0-9_]+_MESSAGE)\s*=\s*"([^"]+)"/gm)) {
    messages.set(match[1], match[2])
  }
  const pairs: Array<{ code: string; message: string }> = []
  for (const [codeName, code] of codes) {
    const messageName = `${codeName.slice(0, -'_CODE'.length)}_MESSAGE`
    const message = messages.get(messageName)
    if (message) {
      pairs.push({ code, message })
    }
  }
  return pairs
}

describe('extractWarnings', () => {
  it('exports machine codes used by the FE/BE frozen catalog', () => {
    expect([
      EXTRACT_LLM_TIMEOUT_CODE,
      EXTRACT_LLM_RATE_LIMITED_CODE,
      EXTRACT_LLM_JSON_INVALID_CODE,
      EXTRACT_SCHEMA_VALIDATION_FAILED_CODE,
      EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE,
      LOW_CONFIDENCE_GRAPH_CODE,
    ]).toEqual([
      'extract_llm_timeout',
      'extract_llm_rate_limited',
      'extract_llm_json_invalid',
      'extract_schema_validation_failed',
      'extract_context_window_exceeded',
      'low_confidence_graph',
    ])
  })

  it('maps extract_heuristic_fallback to frozen user message', () => {
    expect(resolveExtractWarningMessages([EXTRACT_HEURISTIC_FALLBACK_CODE])).toEqual([
      EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('maps mvp_skeleton_preview to frozen MVP skeleton copy', () => {
    expect(resolveExtractWarningMessages([MVP_SKELETON_PREVIEW_CODE])).toEqual([MVP_SKELETON_PREVIEW_MESSAGE])
    expect(resolveExtractWarningDisplays([MVP_SKELETON_PREVIEW_CODE])).toEqual([
      { message: MVP_SKELETON_PREVIEW_MESSAGE },
    ])
  })

  it('registers every backend extract_constants CODE/MESSAGE pair (BE ⊂ FE)', () => {
    const catalog = loadBackendExtractWarningCatalog()
    expect(catalog.length).toBeGreaterThan(0)
    for (const { code, message } of catalog) {
      expect(resolveExtractWarningMessages([code]), `missing FE mapping for ${code}`).toEqual([message])
      expect(resolveExtractWarningDisplays([code])[0]?.technicalCode).toBeUndefined()
    }
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
