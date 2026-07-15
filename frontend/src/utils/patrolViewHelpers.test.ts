/**
 * Unit tests — Part F / F1: four PatrolMode options + product labels.
 * RED until PATROL_MODE_OPTIONS / copy cover method_overlap + claim_evolution.
 */
import { describe, expect, it } from 'vitest'

import type { PatrolMode } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'
import { PATROL_MODE_OPTIONS, patrolModeLabel } from '@/utils/patrolViewHelpers'

const OPENAPI_PATROL_MODES = [
  'lens_clash',
  'contradiction',
  'method_overlap',
  'claim_evolution',
] as const satisfies readonly PatrolMode[]

describe('patrolViewHelpers (F1 unit)', () => {
  it('exposes each OpenAPI PatrolMode once as a selectable option', () => {
    const values = PATROL_MODE_OPTIONS.map((option) => option.value)
    expect(values).toEqual([...OPENAPI_PATROL_MODES])
    expect(new Set(values).size).toBe(OPENAPI_PATROL_MODES.length)
  })

  it('every option carries a product label and caption from baseline copy', () => {
    expect(PATROL_MODE_OPTIONS).toHaveLength(OPENAPI_PATROL_MODES.length)
    for (const option of PATROL_MODE_OPTIONS) {
      expect(option.label.trim().length).toBeGreaterThan(0)
      expect(option.caption.trim().length).toBeGreaterThan(0)
      expect(option.label).not.toBe(option.value)
    }
  })

  it('patrolModeLabel returns product names for all four modes (not raw enums)', () => {
    const copy = patrolBaselineCopyV2()
    expect(patrolModeLabel('lens_clash')).toBe(PATROL_BASELINE_COPY.modeLensClashLabel)
    expect(patrolModeLabel('contradiction')).toBe(PATROL_BASELINE_COPY.modeContradictionLabel)
    expect(patrolModeLabel('method_overlap')).toBe(copy.modeMethodOverlapLabel)
    expect(patrolModeLabel('claim_evolution')).toBe(copy.modeClaimEvolutionLabel)
    expect(patrolModeLabel('method_overlap')).not.toBe('method_overlap')
    expect(patrolModeLabel('claim_evolution')).not.toBe('claim_evolution')
  })
})
