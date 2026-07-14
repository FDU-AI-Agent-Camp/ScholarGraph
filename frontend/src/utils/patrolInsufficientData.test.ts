import { describe, expect, it } from 'vitest'

import type { PatrolInsight } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import {
  exclusionDescription,
  exclusionReasonTitle,
  formatExclusionPhase,
  insufficientDataBadgeLabel,
  isInsufficientDataInsight,
} from '@/utils/patrolInsufficientData'

function makeInsight(overrides: Partial<PatrolInsight> = {}): PatrolInsight {
  return {
    insight_id: 'ins-method-overlap-001',
    title: '方法重叠（Method Overlap）',
    summary: 'fallback summary',
    status: 'insufficient_data',
    paper_ids: ['hss-001', 'hss-002'],
    node_refs: [],
    exclusion_logic: {
      phase: 'PARADIGM_GATE',
      reason_code: 'PARADIGM_UNSUPPORTED',
      description: 'HSS 范式不支持 method_overlap',
      metrics: { required_paradigm: 'STEM' },
    },
    ...overrides,
  }
}

describe('patrolInsufficientData helpers', () => {
  it('detects channel-B insufficient_data insights', () => {
    expect(isInsufficientDataInsight(makeInsight())).toBe(true)
    expect(isInsufficientDataInsight(makeInsight({ status: 'ready', exclusion_logic: null }))).toBe(false)
  })

  it('maps reason_code to Chinese titles', () => {
    expect(exclusionReasonTitle('NO_OVERLAP')).toBe('未检测到方法/数据集重叠')
    expect(exclusionReasonTitle('RQ_GATE_FAILED')).toBe('研究问题未对齐')
    expect(exclusionReasonTitle(undefined)).toBe(PATROL_BASELINE_COPY.insufficientInsightFallbackTitle)
  })

  it('prefers exclusion_logic.description over summary', () => {
    const insight = makeInsight()
    expect(exclusionDescription(insight.exclusion_logic, insight.summary)).toBe(
      'HSS 范式不支持 method_overlap',
    )
    expect(exclusionDescription(null, 'only summary')).toBe('only summary')
  })

  it('exposes badge and phase helpers', () => {
    expect(insufficientDataBadgeLabel()).toBe(PATROL_BASELINE_COPY.insufficientInsightBadge)
    expect(formatExclusionPhase('OVERLAP_MATCH')).toBe('OVERLAP_MATCH')
    expect(formatExclusionPhase('  ')).toBeNull()
  })
})
