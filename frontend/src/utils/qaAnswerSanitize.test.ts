import { describe, expect, it } from 'vitest'

import { sanitizeQaAnswer, sanitizeQaAnswerDelta } from './qaAnswerSanitize'

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
})
