/**
 * Typed access to V2 mode copy keys that F1 must add to PATROL_BASELINE_COPY.
 * Keeps Part F RED tests typecheck-clean before the keys exist at runtime.
 */
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

type V2ModeCopyKeys =
  | 'modeMethodOverlapLabel'
  | 'modeMethodOverlapCaption'
  | 'modeClaimEvolutionLabel'
  | 'modeClaimEvolutionCaption'

export type PatrolBaselineCopyV2 = typeof PATROL_BASELINE_COPY & Record<V2ModeCopyKeys, string>

export function patrolBaselineCopyV2(): PatrolBaselineCopyV2 {
  return PATROL_BASELINE_COPY as PatrolBaselineCopyV2
}
