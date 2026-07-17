/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD A-04 — 图谱 G6 + ?node= 高亮 + 409 未就绪（FE↔BE 成对联调）.
 *
 * 与 tests/integration/test_dod_a01_a04_fe_be.py::TestA04GraphPageContract 成对。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { PaperDetail, UnifiedPaperGraph } from '@/api/types'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { routes } from '@/router/index'
import { buildG6GraphData, buildHighlightStateMap, toG6GraphPayload } from '@/utils/paperGraph'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'

/** BE error code → FE 图谱页行为（§6.1 A-04）. */
const BE_FE_A04 = {
  graphNotReady: { code: 'GRAPH_NOT_READY', httpStatus: 409 },
  paperNotFound: { code: 'PAPER_NOT_FOUND', httpStatus: 404 },
} as const

const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: vi.fn(),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
  uploadPaper: vi.fn(),
  getPaperStatus: vi.fn(),
}))

const readyDetail: PaperDetail = {
  paper_id: 'hss-001',
  title: 'A-04 联调论文',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
  updated_at: '2026-05-19T11:00:00Z',
}

const unifiedGraph = graphFixture.data as UnifiedPaperGraph

const routeStubs = {
  'el-alert': {
    inheritAttrs: false,
    props: ['title', 'description', 'type'],
    template: '<div class="el-alert-stub" v-bind="$attrs" :data-title="title" :data-description="description" />',
  },
  'el-button': {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  GraphToolbar: {
    props: ['disabled'],
    template: '<div class="graph-toolbar-a04" :data-disabled="disabled ? \'true\' : \'false\'" />',
  },
  GraphLegend: { template: '<div class="graph-legend-a04" />' },
  GraphNodeDrawer: { template: '<div class="graph-drawer-a04" />' },
  BadgeParadigm: true,
  PaperGraph: paperGraphSmokeStub,
  RouterLink: true,
}

async function mountGraphRoute(path: string, query?: Record<string, string>) {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(query ? { path, query } : path)
  await router.isReady()
  const wrapper = mount(routerViewShell, {
    global: { plugins: [router], stubs: routeStubs },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('V1 DoD A-04 FE↔BE — graph API contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'a04' } })
    mockGetPaperGraph.mockResolvedValue({
      data: unifiedGraph,
      meta: { request_id: 'a04-graph' },
    })
  })

  it('maps BE GRAPH_NOT_READY (409) to ApiClientError shape used by graph view', () => {
    const error = new ApiClientError({ code: BE_FE_A04.graphNotReady.code, message: '图谱未就绪' }, 409)
    expect(error.code).toBe(BE_FE_A04.graphNotReady.code)
    expect(error.statusCode).toBe(BE_FE_A04.graphNotReady.httpStatus)
  })

  it('toG6GraphPayload + buildHighlightStateMap align with graph-hss fixture node ids', () => {
    const payload = toG6GraphPayload(unifiedGraph)
    const nodeIds = unifiedGraph.nodes.map((node) => node.id)
    const states = buildHighlightStateMap(nodeIds, 'n_lens')

    expect(payload.nodes.some((node) => node.id === 'n_lens')).toBe(true)
    expect(states.n_lens).toBe('active')
    expect(buildG6GraphData(unifiedGraph).nodes.length).toBeGreaterThan(0)
  })
})

describe('V1 DoD A-04 FE↔BE — PaperGraphView UX', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'a04' } })
    mockGetPaperGraph.mockResolvedValue({
      data: unifiedGraph,
      meta: { request_id: 'a04-graph' },
    })
  })

  it('green: loads graph and passes ?node= highlight to PaperGraph', async () => {
    const { wrapper } = await mountGraphRoute('/papers/hss-001/graph', { node: 'n_lens' })

    expect(mockGetPaperGraph).toHaveBeenCalledWith('hss-001')
    const stub = wrapper.find('.paper-graph-smoke-stub')
    expect(stub.attributes('data-highlight')).toBe('n_lens')
    expect(stub.attributes('data-full-bleed')).toBe('true')
    expect(wrapper.find('.graph-view__error-panel').exists()).toBe(false)
    expect(wrapper.find('.graph-toolbar-a04').attributes('data-disabled')).toBe('false')
  })

  it('red: GRAPH_NOT_READY shows baseline title, disables toolbar, hides graph', async () => {
    mockGetPaper.mockResolvedValue({
      data: { ...readyDetail, paper_id: 'hss-002', status: 'processing' },
      meta: { request_id: 'a04-proc' },
    })
    mockGetPaperGraph.mockRejectedValue(
      new ApiClientError({ code: BE_FE_A04.graphNotReady.code, message: '图谱未就绪' }, 409),
    )

    const { wrapper } = await mountGraphRoute('/papers/hss-002/graph')

    const alert = wrapper.find('.graph-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(GRAPH_BASELINE_COPY.graphNotReadyTitle)
    expect(alert.attributes('data-description')).toBe(GRAPH_BASELINE_COPY.graphNotReadyDescription)
    expect(wrapper.find('.graph-toolbar-a04').attributes('data-disabled')).toBe('true')
    expect(wrapper.find('.paper-graph-smoke-stub').exists()).toBe(false)
  })

  it('red: GRAPH_NOT_READY CTA navigates back to paper detail', async () => {
    mockGetPaperGraph.mockRejectedValue(
      new ApiClientError({ code: BE_FE_A04.graphNotReady.code, message: '图谱未就绪' }, 409),
    )
    const { wrapper, router } = await mountGraphRoute('/papers/hss-002/graph')
    const pushSpy = vi.spyOn(router, 'push')

    await wrapper.find('.graph-view__error-cta').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/papers/hss-002')
  })

  it('boundary: unknown ?node= keeps shell without error panel', async () => {
    const { wrapper } = await mountGraphRoute('/papers/hss-001/graph', { node: 'missing-node' })

    expect(wrapper.find('.paper-graph-smoke-stub').attributes('data-highlight')).toBe('missing-node')
    expect(wrapper.find('.graph-view').exists()).toBe(true)
    expect(wrapper.find('.graph-view__error-panel').exists()).toBe(false)
  })

  it('red: GRAPH_NOT_READY uses baseline title not raw API message', async () => {
    mockGetPaperGraph.mockRejectedValue(
      new ApiClientError({ code: BE_FE_A04.graphNotReady.code, message: '内部图谱未就绪' }, 409),
    )

    const { wrapper } = await mountGraphRoute('/papers/hss-002/graph')

    const alert = wrapper.find('.graph-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(GRAPH_BASELINE_COPY.graphNotReadyTitle)
    expect(alert.attributes('data-description')).toBe(GRAPH_BASELINE_COPY.graphNotReadyDescription)
  })

  it('red: non-409 graph error shows raw message without detail CTA', async () => {
    mockGetPaperGraph.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))

    const { wrapper } = await mountGraphRoute('/papers/hss-001/graph')

    expect(wrapper.find('.graph-view__error-cta').exists()).toBe(false)
    expect(wrapper.find('.graph-view__error-panel .el-alert-stub').attributes('data-title')).toBe('服务不可用')
  })
})
