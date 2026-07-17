/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Functional / boundary / 越权 — Part F P1 on production PatrolView.
 * Layout CSS is locked via scoped stylesheet rules (happy-dom cannot compute scoped borders/grids).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_MODE_OPTIONS } from '@/utils/patrolViewHelpers'
import { RouteName } from '@/router/meta'
import { readFrontendSource } from '@/test/helpers/designTokens'
import { PATROL_V2_SUBTITLE, patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'
import patrolMethodOverlapFixture from '../../../docs/api/fixtures/patrol-method-overlap.json'
import patrolMethodOverlapInsufficientFixture from '../../../docs/api/fixtures/patrol-method-overlap-insufficient.json'

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

describe('PatrolView P1 (F4–F6 / F9)', () => {
  const v2Copy = patrolBaselineCopyV2()

  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  describe('F5 subtitle', () => {
    it('renders production four-mode subtitle into the page header', async () => {
      const wrapper = await mountPatrolView()

      expect(wrapper.find('.patrol-view__subtitle').text()).toBe(PATROL_V2_SUBTITLE)
    })
  })

  describe('F6 segmented layout', () => {
    it('renders exactly four mode tabs from PATROL_MODE_OPTIONS (runtime)', async () => {
      const wrapper = await mountPatrolView()
      const tabs = wrapper.findAll('.patrol-mode-segment__item')

      expect(PATROL_MODE_OPTIONS).toHaveLength(4)
      expect(tabs).toHaveLength(4)
      for (const option of PATROL_MODE_OPTIONS) {
        expect(wrapper.text()).toContain(option.label)
      }
    })

    it('keeps desktop 2-column / mobile 1-column grid on production stylesheet', () => {
      // happy-dom does not apply Vue scoped CSS to getComputedStyle; lock the SFC rules instead.
      const viewSrc = readFrontendSource('views/PatrolView.vue')
      expect(viewSrc).toMatch(
        /\.patrol-mode-segment\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
      )
      expect(viewSrc).toMatch(
        /@media\s*\(max-width:\s*768px\)\s*\{[\s\S]*?\.patrol-mode-segment\s*\{[\s\S]*?grid-template-columns:\s*1fr/,
      )
    })
  })

  describe('F4 V2 insight variants in report', () => {
    it('wires report.mode method_overlap onto production InsightCard class', async () => {
      mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('.insight-card--method_overlap').exists()).toBe(true)
    })
  })

  describe('F9 point-level node_refs', () => {
    it('exposes structured point node_refs as graph deep links in the report', async () => {
      mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      const pointLinks = wrapper.findAll('[data-testid="patrol-point-node-ref"]')
      expect(pointLinks.length).toBeGreaterThan(0)
      expect(wrapper.text()).toContain('n_method_pca')
      expect(wrapper.text()).toContain('n_method_pca_full')

      const allowed = new Set(patrolMethodOverlapFixture.data.paper_ids)
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

    it('does not render point-level node_refs on insufficient_data insights (信息隔离)', async () => {
      const polluted = structuredClone(patrolMethodOverlapInsufficientFixture) as DataResponse<PatrolReport>
      const insight = polluted.data.insights[0]
      if (insight) {
        insight.structured_points = [
          {
            mode: 'method_overlap',
            overlap_type: 'method',
            overlap_label: 'LEAKED-POINT',
            paper_a_usage: 'a',
            paper_b_usage: 'b',
            node_refs: [{ paper_id: 'evil-paper', node_id: 'n_evil', label: 'evil-ref' }],
          },
        ]
      }
      mockRunPatrol.mockResolvedValue(polluted)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'hss-001', 'hss-002')
      await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('[data-testid="insufficient-data-insight-card"]').exists()).toBe(true)
      expect(wrapper.findAll('[data-testid="patrol-point-node-ref"]')).toHaveLength(0)
      expect(wrapper.text()).not.toContain('evil-ref')
      expect(wrapper.text()).not.toContain('LEAKED-POINT')
    })
  })
})
