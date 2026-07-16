/**
 * Presentational helpers for PatrolView (D-12 line-budget extract).
 * Mode options / graph-link builders live here so acceptance tests can assert
 * against `PatrolView.vue` + this module as a bundle.
 */

import type { PatrolInsight, PatrolMode, PatrolPoint } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'

const HSS_DEMO_PAIR: readonly [string, string] = ['hss-001', 'hss-002']
const STEM_DEMO_PAIR: readonly [string, string] = ['stem-001', 'stem-002']
const KNOWN_PATROL_MODES = new Set<PatrolMode>(['lens_clash', 'contradiction', 'method_overlap', 'claim_evolution'])

function isExactPair(paperA: string, paperB: string, pair: readonly [string, string]): boolean {
  return paperA === pair[0] && paperB === pair[1]
}

function isKnownDemoPair(paperA: string, paperB: string): boolean {
  return isExactPair(paperA, paperB, HSS_DEMO_PAIR) || isExactPair(paperA, paperB, STEM_DEMO_PAIR)
}

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

/** Demo corpus recommendation for each OpenAPI PatrolMode (F-R1). */
export function recommendedDemoPaperPairForMode(mode: PatrolMode): [string, string] {
  if (mode === 'method_overlap' || mode === 'claim_evolution') {
    return [STEM_DEMO_PAIR[0], STEM_DEMO_PAIR[1]]
  }
  return [HSS_DEMO_PAIR[0], HSS_DEMO_PAIR[1]]
}

/**
 * Swap demo defaults when entering a mode that prefers another paradigm pair.
 * Returns `null` when the current selection is customized or already recommended.
 */
export function applyModeDemoPaperPrefill(mode: PatrolMode, paperA: string, paperB: string): [string, string] | null {
  if (!KNOWN_PATROL_MODES.has(mode) || !isKnownDemoPair(paperA, paperB)) {
    return null
  }
  const recommended = recommendedDemoPaperPairForMode(mode)
  if (isExactPair(paperA, paperB, recommended)) {
    return null
  }
  return recommended
}

/** Hide insight-level graph links already rendered on structured point cards (F-R2). */
export function filterInsightNodeRefsNotCoveredByPoints(
  insightRefs: PatrolNodeRef[],
  points: PatrolPoint[] | undefined,
): PatrolNodeRef[] {
  const coveredKeys = new Set<string>()
  for (const point of points ?? []) {
    const pointRefs = 'node_refs' in point ? point.node_refs : undefined
    for (const ref of pointRefs ?? []) {
      if (isUsablePatrolNodeRef(ref)) {
        coveredKeys.add(patrolNodeRefKey(ref))
      }
    }
  }
  return insightRefs.filter((ref) => !coveredKeys.has(patrolNodeRefKey(ref)))
}
