/** Presentational helpers shared by PatrolView (keeps the view under D-12 line budget). */

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
]

export function patrolModeLabel(value: PatrolMode): string {
  return PATROL_MODE_OPTIONS.find((item) => item.value === value)?.label ?? value
}

export function patrolInsightKey(insight: PatrolInsight): string {
  return insight.insight_id
}

export function patrolNodeRefKey(ref: PatrolInsight['node_refs'][number]): string {
  return `${ref.paper_id}:${ref.node_id}`
}

export function patrolGraphLinkForNodeRef(ref: PatrolInsight['node_refs'][number]) {
  return {
    name: RouteName.PaperGraph,
    params: { paperId: ref.paper_id },
    query: { node: ref.node_id },
  }
}
