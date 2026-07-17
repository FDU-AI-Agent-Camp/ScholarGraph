/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import { QaAnswerDeltaSanitizer, sanitizeQaAnswer, sanitizeQaAnswerDelta } from './qaAnswerSanitize'

describe('qaAnswerSanitize', () => {
  it('removes empty backtick pairs', () => {
    expect(sanitizeQaAnswer('问题``。')).toBe('问题。')
  })

  it('strips inline code spans', () => {
    expect(sanitizeQaAnswerDelta('`RAG-Sequence`')).toBe('RAG-Sequence')
  })

  it('strips bold markers in final pass', () => {
    expect(sanitizeQaAnswer('这是**重点**')).toBe('这是重点')
  })

  it('trims space before CJK punctuation', () => {
    expect(sanitizeQaAnswer('RAG-Token 。')).toBe('RAG-Token。')
  })

  it('cleans user sample regression fragments', () => {
    const dirty = '核心研究问题``。RAG-Token`` ``。多样性`` ``。'
    const cleaned = sanitizeQaAnswer(dirty)
    expect(cleaned).not.toContain('`')
    expect(cleaned).not.toContain('**')
    expect(cleaned).not.toContain(' 。')
  })

  it('streaming sanitizer trims space before CJK punctuation across deltas', () => {
    const sanitizer = new QaAnswerDeltaSanitizer()
    const parts = [sanitizer.feed('RAG-Token`` ``'), sanitizer.feed('。'), sanitizer.flush()]
    const combined = parts.filter(Boolean).join('')
    expect(combined).toBe('RAG-Token。')
    expect(combined).not.toContain(' 。')
  })
})
