/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * F.6 冒烟 T11：前端 fallback 文案冻结与组件展示。
 */
import { describe, expect, it } from 'vitest'

import {
  EXTRACT_HEURISTIC_FALLBACK_CODE,
  EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
  resolveExtractWarningMessages,
} from '@/utils/extractWarnings'

describe('Phase F.6 frontend smoke', () => {
  it('T11: maps extract_heuristic_fallback to frozen user message', () => {
    expect(EXTRACT_HEURISTIC_FALLBACK_MESSAGE).toBe('触发启发式Fallback!')
    expect(resolveExtractWarningMessages([EXTRACT_HEURISTIC_FALLBACK_CODE])).toEqual(['触发启发式Fallback!'])
  })
})
