import { describe, expect, it } from 'vitest'

import {
  countHeadingLevel,
  hasNoOffScaleMarginTop,
  listOffScaleSpacingPxValues,
  SPACING_SCALE_PX,
  usesOnlySpacingTokensOrAllowlistedPx,
} from '@/test/helpers/layoutDiscipline'

describe('layoutDiscipline helper', () => {
  it('SPACING_SCALE_PX matches §1.4.2 scale', () => {
    expect(SPACING_SCALE_PX).toEqual([4, 8, 12, 16, 24, 32, 48, 64])
  })

  it('countHeadingLevel counts h2 in template only', () => {
    const src = `<template><h2>A</h2><h2>B</h2></template><style>h2 { font-size: 20px; }</style>`
    expect(countHeadingLevel(src, 2)).toBe(2)
  })

  it('listOffScaleSpacingPxValues flags magic gap like 13px', () => {
    expect(listOffScaleSpacingPxValues('gap: 13px;', false)).toEqual([13])
    expect(listOffScaleSpacingPxValues('gap: var(--spacing-12);', false)).toEqual([])
    expect(listOffScaleSpacingPxValues('margin-left: 2px;', true)).toEqual([])
  })

  it('hasNoOffScaleMarginTop rejects margin-top: 13px', () => {
    expect(hasNoOffScaleMarginTop('margin-top: 13px;', true)).toBe(false)
    expect(hasNoOffScaleMarginTop('margin-top: var(--spacing-24);', true)).toBe(true)
  })

  it('usesOnlySpacingTokensOrAllowlistedPx delegates to off-scale list', () => {
    expect(usesOnlySpacingTokensOrAllowlistedPx('gap: 13px;', false)).toBe(false)
    expect(usesOnlySpacingTokensOrAllowlistedPx('gap: var(--spacing-12);', false)).toBe(true)
  })
})
