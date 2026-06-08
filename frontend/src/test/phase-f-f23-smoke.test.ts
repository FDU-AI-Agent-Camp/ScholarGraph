/**
 * F.2.3 冒烟：前端 extract_warnings 文案与组件接线静态门禁。
 */
import { describe, expect, it } from 'vitest'

import { EXTRACT_HEURISTIC_FALLBACK_MESSAGE } from '@/utils/extractWarnings'
import { readFrontendSource } from '@/test/helpers/designTokens'

describe('Phase F.2.3 frontend smoke', () => {
  it('extractWarnings maps machine code to frozen user message', () => {
    expect(EXTRACT_HEURISTIC_FALLBACK_MESSAGE).toBe('触发启发式Fallback!')
  })

  it('PaperStatusPanel wires extract_warnings to warning alert and ElMessage', () => {
    const src = readFrontendSource('components/papers/PaperStatusPanel.vue')
    expect(src).toContain('resolveExtractWarningMessages')
    expect(src).toContain('ElMessage.warning')
    expect(src).toContain('status-panel__extract-warning')
  })

  it('PaperDetailView shows persistent graph extract warning alert', () => {
    const src = readFrontendSource('views/PaperDetailView.vue')
    expect(src).toContain('extractWarningMessages')
    expect(src).toContain('detail-graph__extract-warning')
    expect(src).toContain('resolveExtractWarningMessages')
  })

  it('OpenAPI-generated PaperDetail includes extract_warnings', () => {
    const schemaSrc = readFrontendSource('api/generated/schema.d.ts')
    expect(schemaSrc).toContain('extract_warnings?: string[]')
  })
})
