import { describe, expect, it } from 'vitest'

import { PARADIGM_LABELS, getParadigmLabel } from '@/utils/paradigmLabels'

describe('paradigmLabels', () => {
  it('maps HSS and STEM to Chinese labels', () => {
    expect(PARADIGM_LABELS.HSS).toBe('人文社科')
    expect(PARADIGM_LABELS.STEM).toBe('理工科')
    expect(getParadigmLabel('HSS')).toBe('人文社科')
    expect(getParadigmLabel('STEM')).toBe('理工科')
  })

  it('returns unknown label for missing paradigm', () => {
    expect(getParadigmLabel(null)).toBe('未知')
    expect(getParadigmLabel(undefined)).toBe('未知')
    expect(getParadigmLabel('OTHER')).toBe('未知')
  })
})
