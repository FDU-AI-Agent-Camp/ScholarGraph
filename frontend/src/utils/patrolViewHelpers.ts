/**
 * Presentational helpers for PatrolView (D-12 line-budget extract).
 * Mode options / graph-link builders live here so acceptance tests can assert
 * against `PatrolView.vue` + this module as a bundle.
 */

import type { PatrolInsight, PatrolMode } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'

export const PATROL_MODE_OPTIONS = [
  {
    value: 'lens_clash' as const,
    label: PATROL_BASELINE_COPY.modeLensClashLabel,
    caption: PATROL_BASELINE_COPY.modeLensClashCaption,
  },
  {
    value: 'contradiction' as const,
    label: PATROL_BASELINE_COPY.modeContradictionLabel,
    caption: PATROL_BASELINE_COPY.modeContradictionCaption,
  },
  {
    value: 'method_overlap' as const,
    label: PATROL_BASELINE_COPY.modeMethodOverlapLabel,
    caption: PATROL_BASELINE_COPY.modeMethodOverlapCaption,
  },
  {
    value: 'claim_evolution' as const,
    label: PATROL_BASELINE_COPY.modeClaimEvolutionLabel,
    caption: PATROL_BASELINE_COPY.modeClaimEvolutionCaption,
  },
]

export function patrolModeLabel(value: PatrolMode): string {
  return PATROL_MODE_OPTIONS.find((item) => item.value === value)?.label ?? value
}

export function patrolInsightKey(insight: PatrolInsight): string {
  return insight.insight_id
}

export type PatrolNodeRef = PatrolInsight['node_refs'][number]

export function patrolNodeRefKey(ref: PatrolNodeRef): string {
  return `${ref.paper_id}:${ref.node_id}`
}

/** Drop empty paper_id / node_id so UI never deep-links to invalid graph targets. */
export function isUsablePatrolNodeRef(ref: PatrolNodeRef): boolean {
  return Boolean(ref.paper_id?.trim() && ref.node_id?.trim())
}

export function patrolGraphLinkForNodeRef(ref: PatrolNodeRef) {
  return {
    name: RouteName.PaperGraph,
    params: { paperId: ref.paper_id },
    query: { node: ref.node_id },
  }
}
