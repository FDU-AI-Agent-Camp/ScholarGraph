/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Unit / boundary / 越权 — Part F / F12: ContradictionPointCard dedicated display.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { components } from '@/api/types'
import ContradictionPointCard from '@/components/patrol/ContradictionPointCard.vue'

type ContradictionPoint = components['schemas']['ContradictionPoint']

function basePoint(overrides: Partial<ContradictionPoint> = {}): ContradictionPoint {
  return {
    mode: 'contradiction',
    point_a: '论点 A',
    point_b: '论点 B',
    conflict_type: 'empirical',
    ...overrides,
  }
}

describe('ContradictionPointCard (F12 unit)', () => {
  it('renders OpenAPI ContradictionPoint structured fields (接口)', () => {
    const wrapper = mount(ContradictionPointCard, { props: { point: basePoint() } })

    expect(wrapper.html()).toContain('patrol-point-card--contradiction')
    expect(wrapper.text()).toContain('论点 A')
    expect(wrapper.text()).toContain('论点 B')
    expect(wrapper.text()).toContain('empirical')
  })

  it('renders pre-wrapped long conflict text without crashing (boundary)', () => {
    const longConflict = `${'冲突'.repeat(40)}`
    const wrapper = mount(ContradictionPointCard, {
      props: { point: basePoint({ conflict_type: longConflict }) },
    })

    expect(wrapper.text()).toContain(longConflict)
  })

  it('does not surface method_overlap overlap_label smuggled on the object (越权)', () => {
    const polluted = {
      ...basePoint(),
      overlap_label: 'LEAKED-OVERLAP',
    } as ContradictionPoint & { overlap_label: string }

    const wrapper = mount(ContradictionPointCard, { props: { point: polluted } })
    expect(wrapper.text()).not.toContain('LEAKED-OVERLAP')
  })
})
