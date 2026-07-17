/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import {
  contrastRatio,
  parseHexColor,
  relativeLuminance,
  WCAG_AA_TEXT_CONTRAST,
  WCAG_AA_UI_CONTRAST,
} from '@/test/helpers/colorContrast'
import { loadDesignTokenMap } from '@/test/helpers/designTokens'

describe('colorContrast helper', () => {
  it('parseHexColor expands shorthand hex', () => {
    expect(parseHexColor('#abc')).toEqual({ r: 170, g: 187, b: 204 })
    expect(parseHexColor('#111827')).toEqual({ r: 17, g: 24, b: 39 })
  })

  it('relativeLuminance increases for lighter colors', () => {
    expect(relativeLuminance('#111827')).toBeLessThan(relativeLuminance('#ffffff'))
    expect(relativeLuminance('#f1f5f9')).toBeLessThan(relativeLuminance('#ffffff'))
  })

  it('contrastRatio is symmetric and meets WCAG for design tokens', () => {
    const tokens = loadDesignTokenMap()
    const textPrimary = tokens['--color-text-primary'] ?? '#111827'
    const pageBg = tokens['--color-bg-page'] ?? '#f8f9fb'
    const surfaceBg = tokens['--color-bg-surface'] ?? '#ffffff'

    expect(contrastRatio(textPrimary, surfaceBg)).toBe(contrastRatio(surfaceBg, textPrimary))
    expect(contrastRatio(textPrimary, surfaceBg)).toBeGreaterThanOrEqual(WCAG_AA_TEXT_CONTRAST)
    expect(contrastRatio(textPrimary, pageBg)).toBeGreaterThanOrEqual(WCAG_AA_TEXT_CONTRAST)
  })

  it('exports WCAG AA thresholds for §1.4.1 acceptance gates', () => {
    expect(WCAG_AA_TEXT_CONTRAST).toBe(4.5)
    expect(WCAG_AA_UI_CONTRAST).toBe(3)
  })
})
