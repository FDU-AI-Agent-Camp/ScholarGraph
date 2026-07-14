/**
 * Unit / boundary / 越权 — Part F / F12: LensClashPointCard dedicated display.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { components } from '@/api/types'
import LensClashPointCard from '@/components/patrol/LensClashPointCard.vue'

type LensClashPoint = components['schemas']['LensClashPoint']

function basePoint(overrides: Partial<LensClashPoint> = {}): LensClashPoint {
  return {
    mode: 'lens_clash',
    lens_a: '消费社会',
    lens_b: '公共领域',
    clash_aspect: 'ontology',
    ...overrides,
  }
}

describe('LensClashPointCard (F12 unit)', () => {
  it('renders OpenAPI LensClashPoint structured fields (接口)', () => {
    const wrapper = mount(LensClashPointCard, { props: { point: basePoint() } })

    expect(wrapper.html()).toContain('patrol-point-card--lens_clash')
    expect(wrapper.text()).toContain('消费社会')
    expect(wrapper.text()).toContain('公共领域')
    expect(wrapper.text()).toContain('ontology')
  })

  it('still renders empty-aspect strings as visible Clash aspect (boundary)', () => {
    const wrapper = mount(LensClashPointCard, {
      props: { point: basePoint({ clash_aspect: '' }) },
    })

    expect(wrapper.text()).toContain('Lens A')
    expect(wrapper.text()).toContain('消费社会')
  })

  it('does not surface claim_evolution research_question smuggled on the object (越权)', () => {
    const polluted = {
      ...basePoint(),
      research_question: 'LEAKED-RQ',
    } as LensClashPoint & { research_question: string }

    const wrapper = mount(LensClashPointCard, { props: { point: polluted } })
    expect(wrapper.text()).not.toContain('LEAKED-RQ')
  })
})
