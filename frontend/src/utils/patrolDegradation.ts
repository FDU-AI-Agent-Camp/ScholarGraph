/** Patrol RAG degradation helpers (P9 / F8) — first-class is_degraded + profile. */

import type { components } from '@/api/generated/schema'
import type { PatrolInsight, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

export type PatrolDegradationProfile = components['schemas']['PatrolDegradationProfile']
export type PatrolDegradationReason = components['schemas']['PatrolDegradationReason']

const REASON_COPY: Record<PatrolDegradationReason, string> = {
  INDEX_NOT_READY: PATROL_BASELINE_COPY.degradationIndexNotReady,
  QUERY_FAILED: PATROL_BASELINE_COPY.degradationQueryFailed,
  VECTOR_STORE_UNAVAILABLE: PATROL_BASELINE_COPY.degradationStoreUnavailable,
}

/** Collect the first explicit degradation profile from a report (report-level banner). */
export function extractReportDegradation(report: PatrolReport): PatrolDegradationProfile | null {
  for (const insight of report.insights) {
    const profile = resolveInsightDegradation(insight)
    if (profile) {
      return profile
    }
  }
  return null
}

export function resolveInsightDegradation(insight: PatrolInsight): PatrolDegradationProfile | null {
  if (insight.degradation_profile) {
    return insight.degradation_profile
  }
  if (!insight.is_degraded) {
    return null
  }
  return null
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
