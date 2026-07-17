/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Unit / boundary / 越权 — Part F residual F-R1 / F-R2 on production patrolViewHelpers.
 * Imports the real helpers module; asserts exported production functions' behaviour.
 */
import { describe, expect, it } from 'vitest'

import type { PatrolInsight, PatrolMode, PatrolPoint } from '@/api/types'
import * as patrolViewHelpers from '@/utils/patrolViewHelpers'

function requireHelper<K extends string>(
  name: K,
): Extract<(typeof patrolViewHelpers)[keyof typeof patrolViewHelpers], (...args: never[]) => unknown> {
  const fn = (patrolViewHelpers as Record<string, unknown>)[name]
  expect(fn, `production helper ${name} missing (F-R*)`).toBeTypeOf('function')
  return fn as Extract<(typeof patrolViewHelpers)[keyof typeof patrolViewHelpers], (...args: never[]) => unknown>
}

describe('patrolViewHelpers F-R1 demo paper prefill (unit)', () => {
  it('recommendedDemoPaperPairForMode returns STEM pair for V2 modes (接口)', () => {
    const recommendedDemoPaperPairForMode = requireHelper('recommendedDemoPaperPairForMode') as (
      mode: PatrolMode,
    ) => [string, string]
    expect(recommendedDemoPaperPairForMode('method_overlap')).toEqual(['stem-001', 'stem-002'])
    expect(recommendedDemoPaperPairForMode('claim_evolution')).toEqual(['stem-001', 'stem-002'])
  })

  it('recommendedDemoPaperPairForMode returns HSS pair for V1 modes (接口)', () => {
    const recommendedDemoPaperPairForMode = requireHelper('recommendedDemoPaperPairForMode') as (
      mode: PatrolMode,
    ) => [string, string]
    expect(recommendedDemoPaperPairForMode('lens_clash')).toEqual(['hss-001', 'hss-002'])
    expect(recommendedDemoPaperPairForMode('contradiction')).toEqual(['hss-001', 'hss-002'])
  })

  it('applyModeDemoPaperPrefill swaps HSS demo → STEM when entering V2 mode (functional)', () => {
    const applyModeDemoPaperPrefill = requireHelper('applyModeDemoPaperPrefill') as (
      mode: PatrolMode,
      paperA: string,
      paperB: string,
    ) => [string, string] | null
    expect(applyModeDemoPaperPrefill('method_overlap', 'hss-001', 'hss-002')).toEqual(['stem-001', 'stem-002'])
    expect(applyModeDemoPaperPrefill('claim_evolution', 'hss-001', 'hss-002')).toEqual(['stem-001', 'stem-002'])
  })

  it('applyModeDemoPaperPrefill swaps STEM demo → HSS when entering V1 mode (boundary)', () => {
    const applyModeDemoPaperPrefill = requireHelper('applyModeDemoPaperPrefill') as (
      mode: PatrolMode,
      paperA: string,
      paperB: string,
    ) => [string, string] | null
    expect(applyModeDemoPaperPrefill('lens_clash', 'stem-001', 'stem-002')).toEqual(['hss-001', 'hss-002'])
  })

  it('applyModeDemoPaperPrefill does not overwrite a user-customized pair (越权/边界)', () => {
    const applyModeDemoPaperPrefill = requireHelper('applyModeDemoPaperPrefill') as (
      mode: PatrolMode,
      paperA: string,
      paperB: string,
    ) => [string, string] | null
    expect(applyModeDemoPaperPrefill('method_overlap', 'my-paper-a', 'my-paper-b')).toBeNull()
    expect(applyModeDemoPaperPrefill('lens_clash', 'ready-007', 'ready-008')).toBeNull()
  })

  it('applyModeDemoPaperPrefill is a no-op when already on the recommended demo pair (boundary)', () => {
    const applyModeDemoPaperPrefill = requireHelper('applyModeDemoPaperPrefill') as (
      mode: PatrolMode,
      paperA: string,
      paperB: string,
    ) => [string, string] | null
    expect(applyModeDemoPaperPrefill('method_overlap', 'stem-001', 'stem-002')).toBeNull()
    expect(applyModeDemoPaperPrefill('lens_clash', 'hss-001', 'hss-002')).toBeNull()
  })

  it('applyModeDemoPaperPrefill never invents papers for unknown modes (越权)', () => {
    const applyModeDemoPaperPrefill = requireHelper('applyModeDemoPaperPrefill') as (
      mode: PatrolMode,
      paperA: string,
      paperB: string,
    ) => [string, string] | null
    expect(applyModeDemoPaperPrefill('admin_dump' as PatrolMode, 'hss-001', 'hss-002')).toBeNull()
  })
})

describe('patrolViewHelpers F-R2 insight/point node_refs dedupe (unit)', () => {
  const insightRefs: PatrolInsight['node_refs'] = [
    { paper_id: 'stem-001', node_id: 'n_method_pca', label: 'PCA' },
    { paper_id: 'stem-002', node_id: 'n_method_pca_full', label: 'PCA full' },
    { paper_id: 'stem-001', node_id: 'n_unique_insight', label: 'insight-only' },
  ]

  const points: PatrolPoint[] = [
    {
      mode: 'method_overlap',
      overlap_type: 'method',
      overlap_label: 'PCA',
      paper_a_usage: 'a',
      paper_b_usage: 'b',
      node_refs: [
        { paper_id: 'stem-001', node_id: 'n_method_pca', label: 'PCA' },
        { paper_id: 'stem-002', node_id: 'n_method_pca_full', label: 'PCA full' },
      ],
    },
  ]

  it('filterInsightNodeRefsNotCoveredByPoints drops refs also present on points (接口)', () => {
    const filterInsightNodeRefsNotCoveredByPoints = requireHelper('filterInsightNodeRefsNotCoveredByPoints') as (
      insightRefs: PatrolInsight['node_refs'],
      points: PatrolPoint[] | undefined,
    ) => PatrolInsight['node_refs']
    const visible = filterInsightNodeRefsNotCoveredByPoints(insightRefs, points)
    expect(visible.map((r) => `${r.paper_id}:${r.node_id}`)).toEqual(['stem-001:n_unique_insight'])
  })

  it('keeps all insight refs when points have no node_refs (boundary)', () => {
    const filterInsightNodeRefsNotCoveredByPoints = requireHelper('filterInsightNodeRefsNotCoveredByPoints') as (
      insightRefs: PatrolInsight['node_refs'],
      points: PatrolPoint[] | undefined,
    ) => PatrolInsight['node_refs']
    const pointsWithoutRefs: PatrolPoint[] = [
      {
        mode: 'method_overlap',
        overlap_type: 'method',
        overlap_label: 'PCA',
        paper_a_usage: 'a',
        paper_b_usage: 'b',
        node_refs: [],
      },
    ]
    expect(filterInsightNodeRefsNotCoveredByPoints(insightRefs, pointsWithoutRefs)).toHaveLength(3)
  })

  it('ignores malformed point refs when computing coverage (越权/脏数据)', () => {
    const filterInsightNodeRefsNotCoveredByPoints = requireHelper('filterInsightNodeRefsNotCoveredByPoints') as (
      insightRefs: PatrolInsight['node_refs'],
      points: PatrolPoint[] | undefined,
    ) => PatrolInsight['node_refs']
    const dirtyPoints: PatrolPoint[] = [
      {
        mode: 'method_overlap',
        overlap_type: 'method',
        overlap_label: 'PCA',
        paper_a_usage: 'a',
        paper_b_usage: 'b',
        node_refs: [
          { paper_id: '', node_id: 'n_method_pca', label: 'bad' },
          { paper_id: 'stem-001', node_id: 'n_method_pca', label: 'PCA' },
        ],
      },
    ]
    expect(filterInsightNodeRefsNotCoveredByPoints(insightRefs, dirtyPoints).map((r) => r.node_id)).toEqual([
      'n_method_pca_full',
      'n_unique_insight',
    ])
  })
})
