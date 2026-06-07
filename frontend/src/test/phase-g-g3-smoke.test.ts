/**
 * G.3 冒烟：前端 classify_warnings 文案与组件接线静态门禁。
 */
import { describe, expect, it } from 'vitest'

import { CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE } from '@/utils/classifyWarnings'
import { readFrontendSource } from '@/test/helpers/designTokens'

describe('Phase G.3 frontend smoke', () => {
  it('classifyWarnings maps machine code to frozen user message', () => {
    expect(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE).toBe('触发分类启发式Fallback!')
  })

  it('PaperStatusPanel wires classify_warnings to warning alert and ElMessage', () => {
    const src = readFrontendSource('components/papers/PaperStatusPanel.vue')
    expect(src).toContain('resolveClassifyWarningMessages')
    expect(src).toContain('hasClassifierHeuristicFallback')
    expect(src).toContain('ElMessage.warning')
    expect(src).toContain('CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE')
    expect(src).toContain('status-panel__classify-warning')
  })

  it('PaperDetailView shows persistent graph classify warning alert', () => {
    const src = readFrontendSource('views/PaperDetailView.vue')
    expect(src).toContain('classifyWarningMessages')
    expect(src).toContain('detail-graph__classify-warning')
    expect(src).toContain('resolveClassifyWarningMessages')
  })

  it('OpenAPI-generated PaperDetail and PaperStatusData include classify_warnings', () => {
    const schemaSrc = readFrontendSource('api/generated/schema.d.ts')
    expect(schemaSrc).toContain('classify_warnings?: string[]')
  })
})
