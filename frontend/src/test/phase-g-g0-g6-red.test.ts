/**
 * Phase G G.0–G.6 红灯：前端边界 — fixtures / 文案 / 契约。
 */
import { describe, expect, it } from 'vitest'

import type { PaperDetail, PaperStatusData } from '@/api/types'
import {
  CLASSIFIER_HEURISTIC_FALLBACK_CODE,
  CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
  hasClassifierHeuristicFallback,
  resolveClassifyWarningMessages,
} from '@/utils/classifyWarnings'

import classifyFallbackDetailFixture from '../../../docs/api/fixtures/paper-detail-classify-fallback.json'
import classifyFallbackStatusFixture from '../../../docs/api/fixtures/paper-status-classify-fallback.json'

describe('Phase G G.0–G.6 red (frontend)', () => {
  it('G.6 status fixture uses machine code not frozen user message', () => {
    const data = classifyFallbackStatusFixture.data as PaperStatusData
    expect(data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(data.classify_warnings).not.toContain(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
  })

  it('G.6 detail fixture keeps classification free of classify_warnings', () => {
    const data = classifyFallbackDetailFixture.data as PaperDetail
    expect(data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(Object.keys(data.classification ?? {})).toEqual(['paradigm', 'confidence', 'reason'])
    expect(data.classification).not.toHaveProperty('classify_warnings')
  })

  it('G.0/G.3 resolveClassifyWarningMessages never returns machine code as display for known code', () => {
    const messages = resolveClassifyWarningMessages([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(messages).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE])
    expect(messages).not.toContain(CLASSIFIER_HEURISTIC_FALLBACK_CODE)
  })

  it('G.3 empty classify_warnings does not trigger heuristic fallback detection', () => {
    expect(hasClassifierHeuristicFallback([])).toBe(false)
    expect(resolveClassifyWarningMessages([])).toEqual([])
  })

  it('G.2 frozen message must not appear in raw API fixture arrays', () => {
    const statusJson = JSON.stringify(classifyFallbackStatusFixture.data)
    const detailJson = JSON.stringify(classifyFallbackDetailFixture.data)
    expect(statusJson).not.toContain(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
    expect(detailJson).not.toContain(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
  })

  it('G.6 wrong codes are not the frozen classifier fallback code', () => {
    for (const wrong of ['extract_heuristic_fallback', 'Classifier_Heuristic_Fallback', 'classifier_heuristic', '']) {
      expect(wrong).not.toBe(CLASSIFIER_HEURISTIC_FALLBACK_CODE)
    }
  })
})
