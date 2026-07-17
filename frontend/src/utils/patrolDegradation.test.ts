/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import type { PatrolInsight, PatrolReport } from '@/api/types'
import {
  degradationBannerDescription,
  extractReportDegradation,
  insightShowsDegradation,
  resolveInsightDegradation,
  shouldHealPoll,
  SYNTHESIZED_DEGRADATION_TIMESTAMP,
} from '@/utils/patrolDegradation'

const degradedReport: PatrolReport = {
  mode: 'method_overlap',
  paper_ids: ['stem-001', 'stem-002'],
  generated_at: '2026-07-13T19:15:00Z',
  insights: [
    {
      insight_id: 'ins-method-overlap-001',
      title: '方法重叠',
      summary: '图谱比对完成。',
      status: 'ready',
      paper_ids: ['stem-001', 'stem-002'],
      node_refs: [],
      is_degraded: true,
      degradation_profile: {
        component: 'RAG_CONTEXT',
        reason_code: 'INDEX_NOT_READY',
        affected_papers: ['stem-001'],
        severity: 'WARNING',
        timestamp: '2026-07-13T19:15:00Z',
      },
    },
  ],
}

describe('patrolDegradation', () => {
  it('extracts first-class degradation profile from report', () => {
    const profile = extractReportDegradation(degradedReport)
    expect(profile?.reason_code).toBe('INDEX_NOT_READY')
    expect(profile?.affected_papers).toEqual(['stem-001'])
  })

  it('builds banner copy with affected papers', () => {
    const profile = extractReportDegradation(degradedReport)!
    const description = degradationBannerDescription(profile)
    expect(description).toContain('语义索引仍在构建')
    expect(description).toContain('stem-001')
  })

  it('enables heal poll only for INDEX_NOT_READY', () => {
    const profile = extractReportDegradation(degradedReport)
    expect(shouldHealPoll(profile)).toBe(true)
    expect(
      shouldHealPoll({
        component: 'RAG_CONTEXT',
        reason_code: 'QUERY_FAILED',
        affected_papers: ['stem-001'],
        severity: 'WARNING',
        timestamp: '2026-07-13T19:15:00Z',
      }),
    ).toBe(false)
  })

  it('FE-H1 — synthesizes INDEX_NOT_READY when is_degraded without profile (half-contract)', () => {
    const halfContract: PatrolInsight = {
      insight_id: 'ins-half',
      title: '方法重叠',
      summary: '图谱比对完成。',
      status: 'ready',
      paper_ids: ['stem-001', 'stem-002'],
      node_refs: [],
      is_degraded: true,
    }

    const profile = resolveInsightDegradation(halfContract)
    expect(profile).not.toBeNull()
    expect(profile).toEqual({
      component: 'RAG_CONTEXT',
      reason_code: 'INDEX_NOT_READY',
      affected_papers: ['stem-001', 'stem-002'],
      severity: 'WARNING',
      timestamp: SYNTHESIZED_DEGRADATION_TIMESTAMP,
    })
    expect(insightShowsDegradation(halfContract)).toBe(true)
    expect(shouldHealPoll(profile)).toBe(true)
    expect(extractReportDegradation({ ...degradedReport, insights: [halfContract] })).toEqual(profile)
  })

  it('FE-H1 — returns null when neither flag nor profile present', () => {
    const clean: PatrolInsight = {
      insight_id: 'ins-clean',
      title: '方法重叠',
      summary: '图谱比对完成。',
      status: 'ready',
      paper_ids: ['stem-001', 'stem-002'],
      node_refs: [],
      is_degraded: false,
    }
    expect(resolveInsightDegradation(clean)).toBeNull()
    expect(insightShowsDegradation(clean)).toBe(false)
  })
})
