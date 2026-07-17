/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Functional / boundary / authz tests — Part F / F1–F3 (product UI).
 * RED until four-mode selector + structured_points render land in PatrolView.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { ApiClientError } from '@/api/client'
import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import { patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'
import patrolClaimEvolutionFixture from '../../../docs/api/fixtures/patrol-claim-evolution.json'
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
  // Keep InsightCard stubbed: slot content (structured_points) must be provided by PatrolView.
  InsightCard: {
    props: ['variant', 'title', 'insightId', 'summary'],
    template: '<div class="patrol-insight" :data-title="title" :data-variant="variant"><slot /></div>',
  },
  // Intentionally NOT stubbing InsufficientDataInsightCard — leak isolation asserts real card DOM.
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

function modeTabByLabel(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, label: string) {
  return wrapper.findAll('.patrol-mode-segment__item').find((node) => node.text().includes(label))
}

async function selectModeByLabel(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, label: string | undefined) {
  expect(label, 'V2 mode label missing from PATROL_BASELINE_COPY (F1)').toBeTruthy()
  const tab = modeTabByLabel(wrapper, label as string)
  expect(tab, `mode tab not found for label: ${label}`).toBeTruthy()
  await tab!.trigger('click')
}

describe('PatrolView V2 (F1–F3 functional)', () => {
  const v2Copy = patrolBaselineCopyV2()

  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  it('renders four mode selector tabs for all OpenAPI PatrolMode values (F1)', async () => {
    const wrapper = await mountPatrolView()
    const tabs = wrapper.findAll('.patrol-mode-segment__item')

    expect(tabs).toHaveLength(4)
    expect(wrapper.text()).toContain(PATROL_BASELINE_COPY.modeLensClashLabel)
    expect(wrapper.text()).toContain(PATROL_BASELINE_COPY.modeContradictionLabel)
    expect(wrapper.text()).toContain(v2Copy.modeMethodOverlapLabel)
    expect(wrapper.text()).toContain(v2Copy.modeClaimEvolutionLabel)
  })

  it('forwards method_overlap mode in runPatrol body when selected (F1/F3)', async () => {
    mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['stem-001', 'stem-002'], { mode: 'method_overlap' })
  })

  it('forwards claim_evolution mode in runPatrol body when selected (F1/F3)', async () => {
    mockRunPatrol.mockResolvedValue(patrolClaimEvolutionFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeClaimEvolutionLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['stem-001', 'stem-002'], { mode: 'claim_evolution' })
  })

  it('shows product mode badge for method_overlap report (F1)', async () => {
    mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__mode-badge').text()).toBe(v2Copy.modeMethodOverlapLabel)
    expect(wrapper.find('.patrol-view__mode-badge').text()).not.toBe('method_overlap')
  })

  it('renders method_overlap structured_points fields in the report area (F2/F3)', async () => {
    mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('PCA')
    expect(wrapper.text()).toContain('Applied PCA to MNIST pixel vectors before k-NN classification')
    expect(wrapper.text()).toMatch(/0\.99/)
  })

  it('renders claim_evolution structured_points fields in the report area (F2/F3)', async () => {
    mockRunPatrol.mockResolvedValue(patrolClaimEvolutionFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, v2Copy.modeClaimEvolutionLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('PCA 是否提升 MNIST 分类准确率？')
    expect(wrapper.text()).toContain('refined')
    expect(wrapper.text()).toMatch(/82/)
  })

  describe('boundary', () => {
    it('keeps validation gate before any mode POST (exact two papers)', async () => {
      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', '')
      const methodTab = modeTabByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
      if (methodTab) {
        await methodTab.trigger('click')
      }
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(mockRunPatrol).not.toHaveBeenCalled()
    })

    it('still shows degradation banner for V2 mode reports without a second degradation UI (F8 reuse)', async () => {
      mockRunPatrol.mockResolvedValue({
        data: {
          mode: 'method_overlap',
          paper_ids: ['stem-001', 'stem-002'],
          generated_at: '2026-07-14T00:00:00Z',
          insights: [
            {
              insight_id: 'ins-mo-deg',
              title: '方法重叠',
              summary: '图谱比对完成。',
              status: 'ready',
              paper_ids: ['stem-001', 'stem-002'],
              node_refs: [],
              structured_points: [],
              is_degraded: true,
              degradation_profile: {
                component: 'RAG_CONTEXT',
                reason_code: 'INDEX_NOT_READY',
                affected_papers: ['stem-001'],
                severity: 'WARNING',
                timestamp: '2026-07-14T00:00:00Z',
              },
            },
          ],
        },
        meta: { request_id: 'req-v2-deg' },
      } satisfies DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.findAll('.patrol-view__degradation-banner')).toHaveLength(1)
      expect(wrapper.text()).toContain(PATROL_BASELINE_COPY.degradationEvidencePlaceholder)
    })
  })

  describe('接口契约', () => {
    it('never posts a mode outside the OpenAPI PatrolMode enum from UI tabs', async () => {
      mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')

      for (const tab of wrapper.findAll('.patrol-mode-segment__item')) {
        await tab.trigger('click')
        mockRunPatrol.mockClear()
        await wrapper.find('.patrol-run-stub').trigger('click')
        await flushPromises()

        const [, options] = mockRunPatrol.mock.calls.at(-1) ?? []
        expect(options).toEqual(
          expect.objectContaining({
            mode: expect.stringMatching(/^(lens_clash|contradiction|method_overlap|claim_evolution)$/),
          }),
        )
      }
    })

    it('posts exactly the two selected paper ids (no silent expansion)', async () => {
      mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(mockRunPatrol.mock.calls.length).toBeGreaterThan(0)
      for (const [paperIds, options] of mockRunPatrol.mock.calls) {
        expect(paperIds).toEqual(['stem-001', 'stem-002'])
        expect(paperIds).toHaveLength(2)
        expect(options).toEqual(expect.objectContaining({ mode: expect.any(String) }))
      }
    })
  })

  describe('越权与信息边界', () => {
    it('surfaces HTTP 403 without fabricating a report panel', async () => {
      mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'FORBIDDEN', message: '无权访问巡检' }, 403))

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('.patrol-view__report').exists()).toBe(false)
      expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe('无权访问巡检')
      expect(wrapper.text()).not.toContain('PCA')
    })

    it('surfaces HTTP 401 and clears any prior report (no leftover privileged panel)', async () => {
      // Persistent reject after first success — avoids heal-poll consuming a single mockRejectedValueOnce.
      mockRunPatrol
        .mockResolvedValueOnce(patrolMethodOverlapFixture as DataResponse<PatrolReport>)
        .mockRejectedValue(new ApiClientError({ code: 'UNAUTHORIZED', message: '未授权' }, 401))

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()
      expect(wrapper.find('.patrol-view__report').exists()).toBe(true)

      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('.patrol-view__report').exists()).toBe(false)
      expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(false)
      expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe('未授权')
    })

    it('does not render structured_points payload on insufficient_data (paradigm gate / 信息隔离)', async () => {
      const polluted = structuredClone(patrolMethodOverlapInsufficientFixture) as DataResponse<PatrolReport>
      const firstInsight = polluted.data.insights[0]
      if (firstInsight) {
        firstInsight.structured_points = [
          {
            mode: 'method_overlap',
            overlap_type: 'method',
            overlap_label: 'LEAKED-SECRET-METHOD',
            paper_a_usage: 'should-not-render',
            paper_b_usage: 'should-not-render',
            overlap_score: 0.99,
            match_type: 'semantic',
          },
        ]
      }
      mockRunPatrol.mockResolvedValue(polluted)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'hss-001', 'hss-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('[data-testid="insufficient-data-insight-card"]').exists()).toBe(true)
      expect(wrapper.text()).not.toContain('LEAKED-SECRET-METHOD')
      expect(wrapper.text()).not.toContain('should-not-render')
      expect(wrapper.find('[data-testid="patrol-structured-points"]').exists()).toBe(false)
    })

    it('graph deep links from report stay scoped to report paper_ids (F2 node_refs)', async () => {
      mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      const allowedPaperIds = new Set(patrolMethodOverlapFixture.data.paper_ids)
      expect(wrapper.findAll('.router-link-stub').length).toBeGreaterThan(0)
      for (const link of wrapper.findAll('.router-link-stub')) {
        const raw = link.attributes('data-to')
        expect(raw).toBeTruthy()
        const target = JSON.parse(raw!) as { name: string; params: { paperId: string } }
        expect(target.name).toBe(RouteName.PaperGraph)
        expect(allowedPaperIds.has(target.params.paperId)).toBe(true)
      }
    })
  })
})
