/**
 * Integration — Part F residual F-R1～F-R3 against production PatrolView + point cards.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import type { DataResponse, PatrolReport } from '@/api/types'
import MethodOverlapPointCard from '@/components/patrol/MethodOverlapPointCard.vue'
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

describe('Patrol F-R* integration', () => {
  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  it('method_overlap selection prefills STEM, posts that pair, renders Chinese card + deduped refs', async () => {
    mockRunPatrol.mockResolvedValue(mocks.patrolMethodOverlap as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    const tab = wrapper
      .findAll('.patrol-mode-segment__item')
      .find((node) => node.text().includes(PATROL_BASELINE_COPY.modeMethodOverlapLabel))
    await tab!.trigger('click')
    await flushPromises()

    const selects = wrapper.findAll('.patrol-select-stub')
    expect((selects[0]?.element as HTMLInputElement).value).toBe('stem-001')
    expect((selects[1]?.element as HTMLInputElement).value).toBe('stem-002')

    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['stem-001', 'stem-002'], { mode: 'method_overlap' })

    const pointCard = wrapper.findComponent(MethodOverlapPointCard)
    expect(pointCard.exists()).toBe(true)
    expect(pointCard.text()).toContain('PCA')
    expect(pointCard.text()).toContain('MNIST')
    expect(pointCard.text()).not.toContain('Paper A')
    const paperALabel = (PATROL_BASELINE_COPY as Record<string, unknown>).pointFieldPaperA
    expect(paperALabel).toEqual(expect.any(String))
    expect(pointCard.text()).toContain(paperALabel as string)

    const pointKeys = new Set(
      wrapper.findAll('[data-testid="patrol-point-node-ref"]').map((link) => {
        const target = JSON.parse(link.attributes('data-to')!) as {
          params: { paperId: string }
          query: { node: string }
        }
        return `${target.params.paperId}:${target.query.node}`
      }),
    )
    expect(pointKeys.size).toBeGreaterThan(0)
    for (const link of wrapper.findAll('.patrol-view__node-refs .patrol-node-ref')) {
      const target = JSON.parse(link.attributes('data-to')!) as {
        params: { paperId: string }
        query: { node: string }
      }
      expect(pointKeys.has(`${target.params.paperId}:${target.query.node}`)).toBe(false)
    }
  })
})
