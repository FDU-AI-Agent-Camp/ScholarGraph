/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Typed access / expected literals for Part F V2 Patrol copy contracts.
 */
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

type V2ModeCopyKeys =
  | 'modeMethodOverlapLabel'
  | 'modeMethodOverlapCaption'
  | 'modeClaimEvolutionLabel'
  | 'modeClaimEvolutionCaption'

export type PatrolBaselineCopyV2 = typeof PATROL_BASELINE_COPY & Record<V2ModeCopyKeys, string>

/** F5 expected page subtitle — four-mode product summary. */
export const PATROL_V2_SUBTITLE = '跨论文四模式巡检（视角冲突、论点矛盾、方法重叠、观点演进）· 需 2 篇 ready 论文'

export function patrolBaselineCopyV2(): PatrolBaselineCopyV2 {
  return PATROL_BASELINE_COPY as PatrolBaselineCopyV2
}
