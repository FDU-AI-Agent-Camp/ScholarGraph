/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import {
  RAG_INDEX_NOT_READY_CODE,
  RAG_INDEX_NOT_READY_MESSAGE,
  resolveQaStreamWarningMessage,
} from '@/utils/qaStreamWarnings'

describe('qaStreamWarnings (QA-D1)', () => {
  it('maps RAG_INDEX_NOT_READY to graph-only honesty copy', () => {
    expect(
      resolveQaStreamWarningMessage({
        code: RAG_INDEX_NOT_READY_CODE,
        message: 'server English ignored when code registered',
      }),
    ).toBe(RAG_INDEX_NOT_READY_MESSAGE)
    expect(RAG_INDEX_NOT_READY_MESSAGE).toContain('纯图谱子图')
    expect(RAG_INDEX_NOT_READY_MESSAGE).not.toContain('_')
  })

  it('falls back to server message for unknown codes', () => {
    expect(
      resolveQaStreamWarningMessage({
        code: 'mystery_warn',
        message: '服务端降级说明',
      }),
    ).toBe('服务端降级说明')
  })
})
