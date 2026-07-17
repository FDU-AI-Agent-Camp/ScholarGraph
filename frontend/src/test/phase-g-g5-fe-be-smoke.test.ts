/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** G5 冒烟：Phase G 前后端成对测试门禁文件存在。 */
import { describe, expect, it } from 'vitest'

import { readFrontendSource } from '@/test/helpers/designTokens'

describe('Phase G.5 FE↔BE smoke', () => {
  it('phase-g-fe-be integration wires fixtures to classifyWarnings and PaperStatusPanel', () => {
    const src = readFrontendSource('test/phase-g-fe-be.integration.test.ts')
    expect(src).toContain('paper-status-classify-fallback.json')
    expect(src).toContain('paper-detail-classify-fallback.json')
    expect(src).toContain('CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE')
    expect(src).toContain('PaperStatusPanel')
    expect(src).toContain('test_phase_g_fe_be_integration.py')
  })

  it('cross-stack integration covers classify-fallback fixtures', () => {
    const src = readFrontendSource('api/cross-stack.integration.test.ts')
    expect(src).toContain('paper-status-classify-fallback.json')
    expect(src).toContain('paper-detail-classify-fallback.json')
    expect(src).toContain('resolveClassifyWarningMessages')
  })
})
