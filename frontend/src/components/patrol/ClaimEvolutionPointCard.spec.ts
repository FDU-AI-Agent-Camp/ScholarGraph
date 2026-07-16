/**
 * Unit / boundary / 越权 — Part F / F12: ClaimEvolutionPointCard dedicated display.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { components } from '@/api/types'
import ClaimEvolutionPointCard from '@/components/patrol/ClaimEvolutionPointCard.vue'

type ClaimEvolutionPoint = components['schemas']['ClaimEvolutionPoint']

function basePoint(overrides: Partial<ClaimEvolutionPoint> = {}): ClaimEvolutionPoint {
  return {
    mode: 'claim_evolution',
    research_question: 'PCA 是否提升 MNIST 分类准确率？',
    paper_a_claim: 'claim-a',
    paper_b_claim: 'claim-b',
    evolution_type: 'refined',
    problem_fit_score: 82,
    evidence_summary: 'evidence-summary',
    ...overrides,
  }
}

describe('ClaimEvolutionPointCard (F12 unit)', () => {
  it('renders OpenAPI ClaimEvolutionPoint structured fields (接口)', () => {
    const wrapper = mount(ClaimEvolutionPointCard, { props: { point: basePoint() } })

    expect(wrapper.classes().join(' ') + wrapper.html()).toContain('patrol-point-card--claim_evolution')
    expect(wrapper.text()).toContain('PCA 是否提升 MNIST 分类准确率？')
    expect(wrapper.text()).toContain('claim-a')
    expect(wrapper.text()).toContain('claim-b')
    expect(wrapper.text()).toContain('refined')
    expect(wrapper.text()).toContain('82')
    expect(wrapper.text()).toContain('evidence-summary')
  })

  it('omits optional null claim / score rows without crashing (boundary)', () => {
    const wrapper = mount(ClaimEvolutionPointCard, {
      props: {
        point: basePoint({
          paper_a_claim: null,
          paper_b_claim: null,
          evolution_type: null,
          problem_fit_score: null,
          evidence_summary: null,
        }),
      },
    })

    expect(wrapper.text()).toContain('PCA 是否提升 MNIST 分类准确率？')
    expect(wrapper.text()).not.toContain('claim-a')
    expect(wrapper.text()).not.toContain('Fit')
  })

  it('does not render method_overlap field names from a polluted payload (越权)', () => {
    const polluted = {
      ...basePoint(),
      overlap_label: 'SHOULD-NOT-SURFACE',
      paper_a_usage: 'usage-leak',
    } as ClaimEvolutionPoint & { overlap_label: string; paper_a_usage: string }

    const wrapper = mount(ClaimEvolutionPointCard, { props: { point: polluted } })

    expect(wrapper.text()).not.toContain('SHOULD-NOT-SURFACE')
    expect(wrapper.text()).not.toContain('usage-leak')
  })
})
