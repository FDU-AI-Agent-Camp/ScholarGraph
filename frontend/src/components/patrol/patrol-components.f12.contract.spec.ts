/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Functional / interface — Part F / F12: production dedicated Patrol display components.
 * Runtime mount only (no existsSync / source-string lock doubles).
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import type { DataResponse, PatrolPoint, PatrolReport } from '@/api/types'
import ClaimEvolutionPointCard from '@/components/patrol/ClaimEvolutionPointCard.vue'
import ContradictionPointCard from '@/components/patrol/ContradictionPointCard.vue'
import LensClashPointCard from '@/components/patrol/LensClashPointCard.vue'
import MethodOverlapPointCard from '@/components/patrol/MethodOverlapPointCard.vue'
import PatrolStructuredPoints from '@/components/patrol/PatrolStructuredPoints.vue'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import * as mocks from '@/mocks'

const mockRunPatrol = vi.fn()
const mockPush = vi.fn()
const paperStoreState = reactive({
  items: [] as Array<{ paper_id: string; title: string; status: string; paradigm: string }>,
  fetchList: vi.fn().mockResolvedValue(undefined),
})

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-stub" :data-to="JSON.stringify(to)"><slot /></a>',
  },
}))

import PatrolView from '@/views/PatrolView.vue'
import { flushPromises } from '@vue/test-utils'

const globalStubs = {
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<input class="patrol-select-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-option': true,
  'el-button': {
    inheritAttrs: false,
    props: ['loading'],
    template:
      '<button type="button" class="patrol-run-stub" :data-loading="loading ? \'true\' : \'false\'" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-alert': {
    props: ['title', 'description'],
    template: '<div class="patrol-alert" :data-title="title" :data-desc="description ?? \'\'" />',
  },
}

const routerLinkStub = {
  global: {
    stubs: {
      RouterLink: { props: ['to'], template: '<a><slot /></a>' },
    },
  },
}

describe('Patrol display components (F12 production)', () => {
  it('mounts each dedicated OpenAPI point card with its discriminator fields (接口)', () => {
    expect(
      mount(MethodOverlapPointCard, {
        props: {
          point: {
            mode: 'method_overlap',
            overlap_type: 'method',
            overlap_label: 'MO',
            paper_a_usage: 'a',
            paper_b_usage: 'b',
          },
        },
        ...routerLinkStub,
      }).text(),
    ).toContain('MO')
    expect(
      mount(ClaimEvolutionPointCard, {
        props: { point: { mode: 'claim_evolution', research_question: 'RQ' } },
      }).text(),
    ).toContain('RQ')
    expect(
      mount(LensClashPointCard, {
        props: { point: { mode: 'lens_clash', lens_a: 'A', lens_b: 'B', clash_aspect: 'ontology' } },
      }).text(),
    ).toContain('ontology')
    expect(
      mount(ContradictionPointCard, {
        props: { point: { mode: 'contradiction', point_a: 'PA', point_b: 'PB', conflict_type: 'logical' } },
      }).text(),
    ).toContain('logical')
  })

  it('PatrolStructuredPoints dispatches a mixed four-mode list to dedicated cards (functional)', () => {
    const points: PatrolPoint[] = [
      {
        mode: 'method_overlap',
        overlap_type: 'method',
        overlap_label: 'MO-LABEL',
        paper_a_usage: 'a',
        paper_b_usage: 'b',
      },
      {
        mode: 'claim_evolution',
        research_question: 'CE-QUESTION',
        paper_a_claim: 'ca',
        paper_b_claim: 'cb',
      },
      {
        mode: 'lens_clash',
        lens_a: 'LA',
        lens_b: 'LB',
        clash_aspect: 'ontology',
      },
      {
        mode: 'contradiction',
        point_a: 'PA',
        point_b: 'PB',
        conflict_type: 'logical',
      },
    ]

    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...routerLinkStub })

    expect(wrapper.findComponent(MethodOverlapPointCard).exists()).toBe(true)
    expect(wrapper.findComponent(ClaimEvolutionPointCard).exists()).toBe(true)
    expect(wrapper.findComponent(LensClashPointCard).exists()).toBe(true)
    expect(wrapper.findComponent(ContradictionPointCard).exists()).toBe(true)
    expect(wrapper.text()).toContain('MO-LABEL')
    expect(wrapper.text()).toContain('CE-QUESTION')
    expect(wrapper.text()).toContain('LA')
    expect(wrapper.text()).toContain('PA')
  })

  it('PatrolView wires production PatrolStructuredPoints for @/mocks method_overlap (integration)', async () => {
    mockRunPatrol.mockResolvedValue(mocks.patrolMethodOverlap as DataResponse<PatrolReport>)

    const wrapper = mount(PatrolView, { global: { stubs: globalStubs } })
    await flushPromises()
    const selects = wrapper.findAll('.patrol-select-stub')
    await selects[0]?.setValue('stem-001')
    await selects[1]?.setValue('stem-002')
    const tab = wrapper
      .findAll('.patrol-mode-segment__item')
      .find((node) => node.text().includes(PATROL_BASELINE_COPY.modeMethodOverlapLabel))
    await tab!.trigger('click')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(PatrolStructuredPoints).exists()).toBe(true)
    expect(wrapper.findComponent(MethodOverlapPointCard).exists()).toBe(true)
    expect(wrapper.text()).toContain('PCA')
    // View must not inline structured field keys as its own markup — child card owns them.
    expect(wrapper.findComponent(MethodOverlapPointCard).text()).toContain('Applied PCA to MNIST')
  })
})
