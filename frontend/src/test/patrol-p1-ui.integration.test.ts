/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Integration — Part F P1: View → runPatrol → DOM for F4/F5/F9.
 * Uses real runPatrol; spies postData only.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import * as client from '@/api/client'
import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_V2_SUBTITLE, patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'
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
      '<button type="button" class="patrol-run-stub" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-alert': {
    props: ['title', 'description'],
    template: '<div class="patrol-alert" :data-title="title" />',
  },
}

describe('patrol P1 UI integration (F4/F5/F9)', () => {
  beforeEach(() => {
    mockPush.mockReset()
    paperStoreState.fetchList.mockClear()
    vi.restoreAllMocks()
  })

  it('method_overlap fixture surfaces V2 insight variant, subtitle, and point node_refs', async () => {
    const v2Copy = patrolBaselineCopyV2()
    const postSpy = vi
      .spyOn(client, 'postData')
      .mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = mount(PatrolView, { global: { stubs: globalStubs } })
    await flushPromises()

    expect(wrapper.find('.patrol-view__subtitle').text()).toBe(PATROL_V2_SUBTITLE)

    const selects = wrapper.findAll('.patrol-select-stub')
    await selects[0]?.setValue('stem-001')
    await selects[1]?.setValue('stem-002')
    const modeTab = wrapper
      .findAll('.patrol-mode-segment__item')
      .find((node) => node.text().includes(v2Copy.modeMethodOverlapLabel))
    expect(modeTab).toBeTruthy()
    await modeTab!.trigger('click')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['stem-001', 'stem-002'],
      mode: 'method_overlap',
    })
    expect(wrapper.find('.insight-card--method_overlap').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="patrol-point-node-ref"]').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('n_method_pca')
  })
})
