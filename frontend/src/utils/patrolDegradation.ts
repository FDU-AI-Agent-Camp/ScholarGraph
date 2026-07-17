/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** Patrol RAG degradation helpers (P9 / F8 / FE-H1) — SSOT for is_degraded + profile. */

import type { components } from '@/api/generated/schema'
import type { PatrolInsight, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

export type PatrolDegradationProfile = components['schemas']['PatrolDegradationProfile']
export type PatrolDegradationReason = components['schemas']['PatrolDegradationReason']

/** Stable timestamp for synthesized half-contract profiles (demo/CI determinism). */
export const SYNTHESIZED_DEGRADATION_TIMESTAMP = '1970-01-01T00:00:00.000Z' as const

const REASON_COPY: Record<PatrolDegradationReason, string> = {
  INDEX_NOT_READY: PATROL_BASELINE_COPY.degradationIndexNotReady,
  QUERY_FAILED: PATROL_BASELINE_COPY.degradationQueryFailed,
  VECTOR_STORE_UNAVAILABLE: PATROL_BASELINE_COPY.degradationStoreUnavailable,
}

/**
 * Defensive default when BE sets ``is_degraded`` without ``degradation_profile``.
 * Points at INDEX_NOT_READY so Banner + heal poll stay synchronized (FE-H1).
 */
function synthesizeIndexNotReadyProfile(insight: PatrolInsight): PatrolDegradationProfile {
  return {
    component: 'RAG_CONTEXT',
    reason_code: 'INDEX_NOT_READY',
    affected_papers: [...insight.paper_ids],
    severity: 'WARNING',
    timestamp: SYNTHESIZED_DEGRADATION_TIMESTAMP,
  }
}

/** Collect the first degradation profile from a report (report-level banner / heal gate). */
export function extractReportDegradation(report: PatrolReport): PatrolDegradationProfile | null {
  for (const insight of report.insights) {
    const profile = resolveInsightDegradation(insight)
    if (profile) {
      return profile
    }
  }
  return null
}

/**
 * Single source of truth: prefer explicit profile; synthesize INDEX_NOT_READY when
 * only the boolean flag is set so Banner / card placeholder / heal never split-brain.
 */
export function resolveInsightDegradation(insight: PatrolInsight): PatrolDegradationProfile | null {
  if (insight.degradation_profile) {
    return insight.degradation_profile
  }
  if (insight.is_degraded) {
    return synthesizeIndexNotReadyProfile(insight)
  }
  return null
}

export function insightShowsDegradation(insight: PatrolInsight): boolean {
  return resolveInsightDegradation(insight) !== null
}

export function shouldHealPoll(profile: PatrolDegradationProfile | null): boolean {
  return profile?.reason_code === 'INDEX_NOT_READY'
}

export function degradationBannerTitle(profile: PatrolDegradationProfile): string {
  void profile
  return PATROL_BASELINE_COPY.degradationBannerTitle
}

export function degradationBannerDescription(profile: PatrolDegradationProfile): string {
  const reason = REASON_COPY[profile.reason_code] ?? PATROL_BASELINE_COPY.degradationGeneric
  const papers = profile.affected_papers.length ? `受影响论文：${profile.affected_papers.join('、')}。` : ''
  return `${reason}${papers ? ` ${papers}` : ''} ${PATROL_BASELINE_COPY.degradationBannerHint}`
}

export function evidencePlaceholderMessage(): string {
  return PATROL_BASELINE_COPY.degradationEvidencePlaceholder
}

/** Exponential backoff delays in ms for INDEX_NOT_READY heal polling. */
export const PATROL_HEAL_POLL_DELAYS_MS = [10_000, 30_000, 60_000] as const
