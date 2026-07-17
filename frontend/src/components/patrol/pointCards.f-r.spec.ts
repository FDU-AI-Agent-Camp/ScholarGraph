/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Unit / functional / 越权 — Part F residual F-R3 on production *PointCard components.
 * Runtime mount only — no existsSync / source-string locks.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ClaimEvolutionPointCard from '@/components/patrol/ClaimEvolutionPointCard.vue'
import ContradictionPointCard from '@/components/patrol/ContradictionPointCard.vue'
import LensClashPointCard from '@/components/patrol/LensClashPointCard.vue'
import MethodOverlapPointCard from '@/components/patrol/MethodOverlapPointCard.vue'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

const routerLinkStub = {
  global: {
    stubs: {
      RouterLink: { props: ['to'], template: '<a><slot /></a>' },
    },
  },
}

function pointField(key: string): string {
  const value = (PATROL_BASELINE_COPY as Record<string, unknown>)[key]
  expect(value, `PATROL_BASELINE_COPY.${key} must exist for F-R3`).toEqual(expect.any(String))
  return value as string
}

describe('Patrol point cards F-R3 Chinese labels (unit)', () => {
  it('MethodOverlapPointCard renders production Chinese field labels (functional)', () => {
    const wrapper = mount(MethodOverlapPointCard, {
      props: {
        point: {
          mode: 'method_overlap',
          overlap_type: 'method',
          overlap_label: 'PCA',
          paper_a_usage: 'usage-a',
          paper_b_usage: 'usage-b',
          dataset_a: 'MNIST',
          dataset_b: 'MNIST',
          overlap_score: 0.99,
          match_type: 'semantic',
          evidence_summary: 'ev',
        },
      },
      ...routerLinkStub,
    })

    expect(wrapper.classes().join(' ') + wrapper.html()).toContain('patrol-point-card--method_overlap')
    expect(wrapper.findAll('.patrol-point-card__row').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain(pointField('pointFieldPaperA'))
    expect(wrapper.text()).toContain(pointField('pointFieldPaperB'))
    expect(wrapper.text()).toContain(pointField('pointFieldDataset'))
    expect(wrapper.text()).toContain(pointField('pointFieldScore'))
    expect(wrapper.text()).toContain(pointField('pointFieldMatch'))
    expect(wrapper.text()).toContain(pointField('pointFieldEvidence'))
    for (const en of ['Paper A', 'Score', 'Evidence', 'Match', 'Dataset'] as const) {
      expect(wrapper.text()).not.toContain(en)
    }
  })

  it('ClaimEvolution / LensClash / Contradiction cards use Chinese labels (functional)', () => {
    const claim = mount(ClaimEvolutionPointCard, {
      props: {
        point: {
          mode: 'claim_evolution',
          research_question: 'RQ',
          paper_a_claim: 'ca',
          paper_b_claim: 'cb',
          evolution_type: 'refined',
          problem_fit_score: 80,
          evidence_summary: 'ev',
        },
      },
    })
    expect(claim.text()).toContain(pointField('pointFieldPaperA'))
    expect(claim.text()).toContain(pointField('pointFieldFit'))
    expect(claim.text()).toContain(pointField('pointFieldEvidence'))
    expect(claim.text()).not.toContain('Fit')

    const lens = mount(LensClashPointCard, {
      props: {
        point: { mode: 'lens_clash', lens_a: 'LA', lens_b: 'LB', clash_aspect: 'ontology' },
      },
    })
    expect(lens.findAll('.patrol-point-card__row').length).toBe(3)
    expect(lens.text()).toContain(pointField('pointFieldLensA'))
    expect(lens.text()).toContain(pointField('pointFieldAspect'))
    expect(lens.text()).not.toContain('Lens A')

    const contradiction = mount(ContradictionPointCard, {
      props: {
        point: { mode: 'contradiction', point_a: 'PA', point_b: 'PB', conflict_type: 'logical' },
      },
    })
    expect(contradiction.text()).toContain(pointField('pointFieldPointA'))
    expect(contradiction.text()).toContain(pointField('pointFieldConflict'))
    expect(contradiction.text()).not.toContain('Point A')
  })

  it('all four cards share the same production layout class tokens (接口/一致性)', () => {
    const mounts = [
      mount(MethodOverlapPointCard, {
        props: {
          point: {
            mode: 'method_overlap',
            overlap_type: 'method',
            overlap_label: 'X',
            paper_a_usage: 'a',
            paper_b_usage: 'b',
          },
        },
        ...routerLinkStub,
      }),
      mount(ClaimEvolutionPointCard, {
        props: { point: { mode: 'claim_evolution', research_question: 'RQ' } },
      }),
      mount(LensClashPointCard, {
        props: { point: { mode: 'lens_clash', lens_a: 'A', lens_b: 'B', clash_aspect: 'ontology' } },
      }),
      mount(ContradictionPointCard, {
        props: { point: { mode: 'contradiction', point_a: 'A', point_b: 'B', conflict_type: 'logical' } },
      }),
    ]

    for (const wrapper of mounts) {
      expect(wrapper.classes().some((c) => c.startsWith('patrol-point-card'))).toBe(true)
      expect(wrapper.html()).toContain('patrol-point-card__')
    }
  })

  it('does not surface English leftover labels when optional fields are present (越权)', () => {
    const wrapper = mount(MethodOverlapPointCard, {
      props: {
        point: {
          mode: 'method_overlap',
          overlap_type: 'method',
          overlap_label: 'PCA',
          paper_a_usage: 'a',
          paper_b_usage: 'b',
          evidence_summary: 'ev',
          overlap_score: 1,
          match_type: 'literal',
        },
      },
      ...routerLinkStub,
    })
    expect(wrapper.text()).toMatch(/论文|证据|重叠|匹配/)
    expect(wrapper.text()).not.toMatch(/\b(Paper A|Score|Evidence|Match)\b/)
  })
})
