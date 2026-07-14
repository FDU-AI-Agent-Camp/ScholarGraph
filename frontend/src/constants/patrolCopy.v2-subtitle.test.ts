/**
 * Unit — Part F / F5: production PATROL_BASELINE_COPY.subtitle four-mode copy.
 */
import { describe, expect, it } from 'vitest'

import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { PATROL_V2_SUBTITLE } from '@/test/helpers/patrolV2Copy'

describe('PATROL_BASELINE_COPY V2 subtitle (F5 unit)', () => {
  it('subtitle is the four-mode product summary (not V1 clash/contradiction-only text)', () => {
    expect(PATROL_BASELINE_COPY.subtitle).toBe(PATROL_V2_SUBTITLE)
    expect(PATROL_BASELINE_COPY.subtitle).toContain('方法重叠')
    expect(PATROL_BASELINE_COPY.subtitle).toContain('观点演进')
    expect(PATROL_BASELINE_COPY.subtitle).toContain('视角冲突')
    expect(PATROL_BASELINE_COPY.subtitle).toContain('论点矛盾')
    expect(PATROL_BASELINE_COPY.subtitle).toMatch(/ready/)
  })
})
