/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Functional / boundary / 越权 — Part F residual F-R1 / F-R2 on production PatrolView.
 * RED until STEM prefill on mode change + insight/point node_refs dedupe land.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import patrolMethodOverlapFixture from '../../../docs/api/fixtures/patrol-method-overlap.json'

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

function paperSelection(wrapper: Awaited<ReturnType<typeof mountPatrolView>>): [string, string] {
  const selects = wrapper.findAll('.patrol-select-stub')
  return [(selects[0]?.element as HTMLInputElement).value, (selects[1]?.element as HTMLInputElement).value]
}

async function selectModeByLabel(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, label: string) {
  const tab = wrapper.findAll('.patrol-mode-segment__item').find((node) => node.text().includes(label))
  expect(tab, `missing mode tab: ${label}`).toBeTruthy()
  await tab!.trigger('click')
  await flushPromises()
}

function linkKeys(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, testId?: string): string[] {
  const nodes = testId ? wrapper.findAll(`[data-testid="${testId}"]`) : wrapper.findAll('.patrol-node-ref')
  return nodes.map((link) => {
    const target = JSON.parse(link.attributes('data-to')!) as {
      params: { paperId: string }
      query: { node: string }
    }
    return `${target.params.paperId}:${target.query.node}`
  })
}

describe('PatrolView F-R1 STEM/HSS demo prefill (functional)', () => {
  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  it('defaults to HSS demo pair on first paint (boundary)', async () => {
    const wrapper = await mountPatrolView()
    expect(paperSelection(wrapper)).toEqual(['hss-001', 'hss-002'])
  })

  it('prefills STEM demo pair when switching to method_overlap (functional)', async () => {
    const wrapper = await mountPatrolView()
    expect(paperSelection(wrapper)).toEqual(['hss-001', 'hss-002'])

    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    expect(paperSelection(wrapper)).toEqual(['stem-001', 'stem-002'])
  })

  it('prefills STEM demo pair when switching to claim_evolution (functional)', async () => {
    const wrapper = await mountPatrolView()
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeClaimEvolutionLabel)
    expect(paperSelection(wrapper)).toEqual(['stem-001', 'stem-002'])
  })

  it('restores HSS demo pair when leaving STEM mode for lens_clash (boundary)', async () => {
    const wrapper = await mountPatrolView()
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    expect(paperSelection(wrapper)).toEqual(['stem-001', 'stem-002'])

    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeLensClashLabel)
    expect(paperSelection(wrapper)).toEqual(['hss-001', 'hss-002'])
  })

  it('does not overwrite a customized paper pair when switching modes (越权)', async () => {
    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'custom-a', 'custom-b')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    expect(paperSelection(wrapper)).toEqual(['custom-a', 'custom-b'])
  })
})

describe('PatrolView F-R2 insight/point node_refs dedupe (functional)', () => {
  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  it('hides insight-level graph links that already appear on point cards (functional)', async () => {
    mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const pointKeys = new Set(linkKeys(wrapper, 'patrol-point-node-ref'))
    expect(pointKeys.size).toBeGreaterThan(0)

    // Insight-level anchors live under .patrol-view__node-refs (not point testid).
    const insightKeyList = wrapper.findAll('.patrol-view__node-refs .patrol-node-ref').map((link) => {
      const target = JSON.parse(link.attributes('data-to')!) as {
        params: { paperId: string }
        query: { node: string }
      }
      return `${target.params.paperId}:${target.query.node}`
    })

    for (const key of insightKeyList) {
      expect(pointKeys.has(key), `duplicate graph link still visible at insight level: ${key}`).toBe(false)
    }
    // Fixture overlap: both insight and point list PCA refs — after dedupe no PCA remains at insight level.
    expect(insightKeyList.some((k) => k.includes('n_method_pca'))).toBe(false)
    expect(wrapper.findAll('[data-testid="patrol-point-node-ref"]').length).toBeGreaterThan(0)
  })

  it('still renders unique insight-only refs after point coverage (boundary)', async () => {
    const fixture = structuredClone(patrolMethodOverlapFixture) as DataResponse<PatrolReport>
    const insight = fixture.data.insights[0]
    if (insight) {
      insight.node_refs = [
        ...insight.node_refs,
        { paper_id: 'stem-001', node_id: 'n_unique_only', label: 'UNIQUE-INSIGHT-REF' },
      ]
    }
    mockRunPatrol.mockResolvedValue(fixture)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('UNIQUE-INSIGHT-REF')
    const insightLinks = wrapper.findAll('.patrol-view__node-refs .patrol-node-ref')
    const keys = insightLinks.map((link) => {
      const target = JSON.parse(link.attributes('data-to')!) as {
        params: { paperId: string }
        query: { node: string }
      }
      return `${target.params.paperId}:${target.query.node}`
    })
    expect(keys).toContain('stem-001:n_unique_only')
    expect(keys).not.toContain('stem-001:n_method_pca')
  })

  it('keeps all insight refs when points have empty node_refs (boundary / 无点级覆盖)', async () => {
    const fixture = structuredClone(patrolMethodOverlapFixture) as DataResponse<PatrolReport>
    const insight = fixture.data.insights[0]
    if (insight?.structured_points?.[0] && insight.structured_points[0].mode === 'method_overlap') {
      insight.structured_points[0].node_refs = []
    }
    mockRunPatrol.mockResolvedValue(fixture)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    await selectModeByLabel(wrapper, PATROL_BASELINE_COPY.modeMethodOverlapLabel)
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const insightLinks = wrapper.findAll('.patrol-view__node-refs .patrol-node-ref')
    expect(insightLinks.length).toBe(fixture.data.insights[0]?.node_refs.length)
    expect(wrapper.findAll('[data-testid="patrol-point-node-ref"]')).toHaveLength(0)
    for (const link of insightLinks) {
      const target = JSON.parse(link.attributes('data-to')!) as { name: string }
      expect(target.name).toBe(RouteName.PaperGraph)
    }
  })
})
