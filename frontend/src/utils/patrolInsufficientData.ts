/**
 * Channel-B insufficient_data presentation helpers (P11 / F7).
 * Distinct from channel-A 422 PATROL_INSUFFICIENT_DATA (patrolForm.ts).
 */

import type { PatrolExclusionLogic, PatrolExclusionReason, PatrolInsight } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

const REASON_TITLES: Record<PatrolExclusionReason, string> = {
  MISSING_REQUIRED_NODES: '缺少必要图谱节点',
  PARADIGM_UNSUPPORTED: '范式不适用',
  NO_OVERLAP: '未检测到方法/数据集重叠',
  RQ_GATE_FAILED: '研究问题未对齐',
  NO_RECALLABLE_CLAIMS: '无法召回结论证据',
}

export function isInsufficientDataInsight(insight: PatrolInsight): boolean {
  return insight.status === 'insufficient_data'
}

export function insufficientDataBadgeLabel(): string {
  return PATROL_BASELINE_COPY.insufficientInsightBadge
}

export function exclusionReasonTitle(reasonCode: PatrolExclusionReason | undefined): string {
  if (!reasonCode) {
    return PATROL_BASELINE_COPY.insufficientInsightFallbackTitle
  }
  return REASON_TITLES[reasonCode] ?? PATROL_BASELINE_COPY.insufficientInsightFallbackTitle
}

export function exclusionDescription(logic: PatrolExclusionLogic | null | undefined, summary: string): string {
  const fromLogic = logic?.description?.trim()
  if (fromLogic) {
    return fromLogic
  }
  return summary
}

export function formatExclusionPhase(phase: string | undefined): string | null {
  if (!phase?.trim()) {
    return null
  }
  return phase.trim()
}
