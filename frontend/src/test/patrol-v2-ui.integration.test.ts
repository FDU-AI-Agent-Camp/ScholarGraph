/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Integration — Part F / F1–F3.
 * Production chain: PatrolView (real) → runPatrol (real) → postData (spy) → report DOM.
 * Does not re-assert fixture JSON shape (that belongs to OpenAPI/fixture contract tests).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import * as client from '@/api/client'
import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'
import { PATROL_MODE_OPTIONS } from '@/utils/patrolViewHelpers'
import patrolClaimEvolutionFixture from '../../../docs/api/fixtures/patrol-claim-evolution.json'
import patrolMethodOverlapFixture from '../../../docs/api/fixtures/patrol-method-overlap.json'

const mockPush = vi.fn()

const paperStoreState = reactive({
  items: [] as Array<{ paper_id: string; title: string; status: string; paradigm: string }>,
  fetchList: vi.fn().mockResolvedValue(undefined),
})

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

// Real runPatrol — do not mock @/api/patrol.
import PatrolView from '@/views/PatrolView.vue'

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

async function mountPatrolView() {
  const wrapper = mount(PatrolView, { global: { stubs: globalStubs } })
  await flushPromises()
  return wrapper
}

async function setPaperSelection(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, paperA: string, paperB: string) {
  const selects = wrapper.findAll('.patrol-select-stub')
  await selects[0]?.setValue(paperA)
  await selects[1]?.setValue(paperB)
  await flushPromises()
}

async function selectModeByLabel(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, label: string) {
  const tab = wrapper.findAll('.patrol-mode-segment__item').find((node) => node.text().includes(label))
  expect(tab, `missing mode tab for product label: ${label}`).toBeTruthy()
  await tab!.trigger('click')
}

describe('patrol V2 UI integration (F1–F3)', () => {
  beforeEach(() => {
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
    vi.restoreAllMocks()
  })

  it('UI method_overlap selection posts mode and renders structured fields from production view', async () => {
    expect(PATROL_MODE_OPTIONS.map((o) => o.value)).toContain('method_overlap')
    const v2Copy = patrolBaselineCopyV2()
    expect(v2Copy.modeMethodOverlapLabel).toBeTruthy()

    const postSpy = vi
      .spyOn(client, 'postData')
      .mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['stem-001', 'stem-002'],
      mode: 'method_overlap',
    })
    expect(wrapper.find('.patrol-view__mode-badge').text()).toBe(v2Copy.modeMethodOverlapLabel)
    expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('PCA')
    expect(wrapper.text()).toContain('Applied PCA to MNIST pixel vectors before k-NN classification')
  })

  it('UI claim_evolution selection posts mode and renders structured fields from production view', async () => {
    expect(PATROL_MODE_OPTIONS.map((o) => o.value)).toContain('claim_evolution')
    const v2Copy = patrolBaselineCopyV2()
    expect(v2Copy.modeClaimEvolutionLabel).toBeTruthy()

    const postSpy = vi
      .spyOn(client, 'postData')
      .mockResolvedValue(patrolClaimEvolutionFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeClaimEvolutionLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['stem-001', 'stem-002'],
      mode: 'claim_evolution',
    })
    expect(wrapper.find('.patrol-view__mode-badge').text()).toBe(v2Copy.modeClaimEvolutionLabel)
    expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('PCA 是否提升 MNIST 分类准确率？')
    expect(wrapper.text()).toContain('refined')
  })

  it('validation still blocks POST when paper selection incomplete under V2 mode options', async () => {
    const postSpy = vi.spyOn(client, 'postData')

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', '')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(postSpy).not.toHaveBeenCalled()
    expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
  })
})
