import { describe, expect, it } from 'vitest'

import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

import {
  buildPatrolPaperIds,
  formatPatrolError,
  parsePatrolPaperIds,
  resolvePatrolApiError,
  validatePatrolPaperIds,
  validatePatrolSelection,
} from './patrolForm'

describe('parsePatrolPaperIds', () => {
  it('splits comma-separated ids and trims whitespace', () => {
    expect(parsePatrolPaperIds(' hss-001 , hss-002 ')).toEqual(['hss-001', 'hss-002'])
  })

  it('returns empty array for blank input', () => {
    expect(parsePatrolPaperIds('  ,  ')).toEqual([])
  })
})

describe('validatePatrolSelection', () => {
  it('requires two distinct paper ids with baseline copy', () => {
    expect(validatePatrolSelection('', 'hss-002')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
    expect(validatePatrolSelection('hss-001', '')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
    expect(validatePatrolSelection('hss-001', 'hss-001')).toBe(PATROL_BASELINE_COPY.validationDuplicate('hss-001'))
    expect(validatePatrolSelection('hss-001', 'hss-002')).toBeNull()
  })
})

describe('validatePatrolPaperIds', () => {
  it('requires exactly two distinct paper ids', () => {
    expect(validatePatrolPaperIds(['hss-001'])).toBe(PATROL_BASELINE_COPY.validationExactTwo)
    expect(validatePatrolPaperIds(['hss-001', 'hss-002', 'hss-003'])).toBe(PATROL_BASELINE_COPY.validationExactTwo)
    expect(validatePatrolPaperIds(['hss-001', 'hss-001'])).toBe(PATROL_BASELINE_COPY.validationDuplicate('hss-001'))
    expect(validatePatrolPaperIds(['hss-001', 'hss-002'])).toBeNull()
  })
})

describe('buildPatrolPaperIds', () => {
  it('trims whitespace from dual select values', () => {
    expect(buildPatrolPaperIds(' hss-001 ', ' hss-002 ')).toEqual(['hss-001', 'hss-002'])
  })
})

describe('resolvePatrolApiError', () => {
  it('maps GRAPH_NOT_READY to baseline title and papers CTA', () => {
    const presentation = resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪')
    expect(presentation.title).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
    expect(presentation.ctaLabel).toBe(PATROL_BASELINE_COPY.graphNotReadyCta)
    expect(presentation.ctaKind).toBe('papers')
  })

  it('maps PATROL_INSUFFICIENT_DATA to baseline title and reset-selection CTA', () => {
    const presentation = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
    expect(presentation.title).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(presentation.description).toBe(PATROL_BASELINE_COPY.insufficientDataDescription)
    expect(presentation.ctaLabel).toBe(PATROL_BASELINE_COPY.insufficientDataCta)
    expect(presentation.ctaKind).toBe('reset-selection')
  })

  it('returns API message for unknown codes', () => {
    expect(resolvePatrolApiError('PATROL_FAILED', '巡检失败').title).toBe('巡检失败')
  })
})

describe('formatPatrolError', () => {
  it('joins baseline title and description for legacy callers', () => {
    expect(formatPatrolError('GRAPH_NOT_READY', '图谱未就绪')).toContain(PATROL_BASELINE_COPY.graphNotReadyTitle)
    expect(formatPatrolError('PATROL_INSUFFICIENT_DATA', '数据不足')).toContain(
      PATROL_BASELINE_COPY.insufficientDataTitle,
    )
  })

  it('returns title only when description is absent', () => {
    expect(formatPatrolError('PATROL_FAILED', '巡检失败')).toBe('巡检失败')
  })
})
