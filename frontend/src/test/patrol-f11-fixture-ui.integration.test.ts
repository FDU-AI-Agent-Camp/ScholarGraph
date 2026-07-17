/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Integration — Part F / F11: production UI consumes @/mocks (canonical fixtures).
 * Only mounts production PatrolView / PatrolStructuredPoints; mocks are data only.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import type { DataResponse, PatrolInsight, PatrolPoint, PatrolReport } from '@/api/types'
import PatrolStructuredPoints from '@/components/patrol/PatrolStructuredPoints.vue'
import * as mocks from '@/mocks'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'

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

const routerLinkStub = {
  global: {
    stubs: {
      RouterLink: {
        props: ['to'],
        template: '<a class="router-link-stub" :data-to="JSON.stringify(to)"><slot /></a>',
      },
    },
  },
}

function pointsFromMock(fixture: DataResponse<PatrolReport>): PatrolPoint[] {
  const insight = fixture.data.insights[0] as PatrolInsight | undefined
  return insight?.structured_points ?? []
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
  expect(tab).toBeTruthy()
  await tab!.trigger('click')
}

describe('F11 V2 fixture → production UI', () => {
  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  it('PatrolStructuredPoints renders method_overlap fields from @/mocks fixture (integration)', () => {
    const points = pointsFromMock(mocks.patrolMethodOverlap as DataResponse<PatrolReport>)
    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...routerLinkStub })

    expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('PCA')
    expect(wrapper.text()).toContain('MNIST')
    expect(wrapper.html()).toContain('patrol-point-card--method_overlap')
  })

  it('PatrolStructuredPoints renders claim_evolution fields from @/mocks fixture (integration)', () => {
    const points = pointsFromMock(mocks.patrolClaimEvolution as DataResponse<PatrolReport>)
    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...routerLinkStub })

    expect(wrapper.text()).toContain('PCA 是否提升 MNIST 分类准确率？')
    expect(wrapper.html()).toContain('patrol-point-card--claim_evolution')
  })

  it('PatrolView run path surfaces @/mocks method_overlap structured_points (functional)', async () => {
    mockRunPatrol.mockResolvedValue(mocks.patrolMethodOverlap as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['stem-001', 'stem-002'], { mode: 'method_overlap' })
    const pointsRoot = wrapper.find('[data-testid="patrol-structured-points"]')
    expect(pointsRoot.exists()).toBe(true)
    expect(pointsRoot.text()).toContain('PCA')
    expect(pointsRoot.text()).toContain('同义词方法标签在共享 MNIST 数据集上共振')
  })

  it('point-level node_refs from fixture deep-link via production PaperGraph route (接口)', async () => {
    mockRunPatrol.mockResolvedValue(mocks.patrolMethodOverlap as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const allowed = new Set(mocks.patrolMethodOverlap.data.paper_ids)
    const pointLinks = wrapper.findAll('[data-testid="patrol-point-node-ref"]')
    expect(pointLinks.length).toBeGreaterThan(0)
    for (const link of pointLinks) {
      const target = JSON.parse(link.attributes('data-to')!) as {
        name: string
        params: { paperId: string }
        query: { node: string }
      }
      expect(target.name).toBe(RouteName.PaperGraph)
      expect(allowed.has(target.params.paperId)).toBe(true)
      expect(target.query.node).toBeTruthy()
    }
  })

  it('does not render structured_points when @/mocks insufficient fixture is returned (越权/信息隔离)', async () => {
    // Channel-B insufficient fixture has no ready-status points path in production view.
    const { default: insufficient } = await import('../../../docs/api/fixtures/patrol-method-overlap-insufficient.json')
    mockRunPatrol.mockResolvedValue(insufficient as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'hss-001', 'hss-002')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="insufficient-data-insight-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(false)
  })
})
