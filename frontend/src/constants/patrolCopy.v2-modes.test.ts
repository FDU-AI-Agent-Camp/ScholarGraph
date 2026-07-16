/**
 * Unit tests — Part F / F1(+F5 copy keys): V2 mode labels required by the selector.
 * RED until PATROL_BASELINE_COPY grows method_overlap / claim_evolution keys.
 */
import { describe, expect, it } from 'vitest'

import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'

describe('PATROL_BASELINE_COPY V2 mode keys (F1 unit)', () => {
  it('defines method_overlap product label and caption', () => {
    expect(PATROL_BASELINE_COPY).toHaveProperty('modeMethodOverlapLabel')
    expect(PATROL_BASELINE_COPY).toHaveProperty('modeMethodOverlapCaption')
    const copy = patrolBaselineCopyV2()
    expect(copy.modeMethodOverlapLabel.trim().length).toBeGreaterThan(0)
    expect(copy.modeMethodOverlapCaption.trim().length).toBeGreaterThan(0)
    expect(copy.modeMethodOverlapLabel).not.toBe('method_overlap')
  })

  it('defines claim_evolution product label and caption', () => {
    expect(PATROL_BASELINE_COPY).toHaveProperty('modeClaimEvolutionLabel')
    expect(PATROL_BASELINE_COPY).toHaveProperty('modeClaimEvolutionCaption')
    const copy = patrolBaselineCopyV2()
    expect(copy.modeClaimEvolutionLabel.trim().length).toBeGreaterThan(0)
    expect(copy.modeClaimEvolutionCaption.trim().length).toBeGreaterThan(0)
    expect(copy.modeClaimEvolutionLabel).not.toBe('claim_evolution')
  })
})
