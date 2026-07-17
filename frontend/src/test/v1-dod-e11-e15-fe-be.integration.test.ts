/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD §6.5 E-11～E-15 — 边界鲁棒性前后端联调联试（FE 侧）.
 *
 * 与 tests/integration/test_dod_e11_e15_fe_be.py 成对验收。
 */
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { PaperDetail, PatrolReport, QaStreamCitationData } from '@/api/types'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { processingStatus, statusResponse } from '@/test/fixtures/paperStatus'
import EmptyState from '@/components/ui/EmptyState.vue'
import { usePaperStatus } from '@/composables/usePaperStatus'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { routerViewShell } from '@/test/helpers/routerViewShell'

const MOCK_DISCLAIMER = '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）'

/** BE 行为 → FE 展示（§6.5 E-11～E-15）. */
const BE_FE_E11_E15 = {
  E11: { mockDisclaimer: MOCK_DISCLAIMER, noErrorPrefix: '错误:' },
  E13: { statusUnavailable: 'PIPELINE_STATUS_UNAVAILABLE' },
  E14: {
    papersEmptyTitle: PAPERS_BASELINE_COPY.emptyTitle,
    papersEmptyBody: PAPERS_BASELINE_COPY.emptyBody,
    patrolReportTitle: PATROL_BASELINE_COPY.reportTitle,
  },
  E15: { serverMessage: '服务不可用', elMessageCode: 'SERVER' },
} as const

const mockListPapers = vi.hoisted(() => vi.fn())
const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())
const mockGetPaperStatus = vi.hoisted(() => vi.fn())
const mockGetPaperStatusForComposable = vi.hoisted(() => vi.fn())
const mockStreamPaperQa = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())
const elMessageError = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
  getPaperStatus: (...args: unknown[]) => {
    mockGetPaperStatus(...args)
    return mockGetPaperStatusForComposable(...args)
  },
}))

vi.mock('@/api/qaStream', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/qaStream')>()
  return {
    ...actual,
    streamPaperQa: (...args: unknown[]) => mockStreamPaperQa(...args),
  }
})

vi.mock('@/api/patrol', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/patrol')>()
  return {
    ...actual,
    runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: {
    error: (...args: unknown[]) => elMessageError(...args),
    warning: vi.fn(),
    success: vi.fn(),
  },
}))

function dispatchSseFrames(
  frames: ReadonlyArray<{ event: string; data: Record<string, unknown> }>,
  handlers: {
    onMessage?: (data: { delta: string }) => void
    onCitation?: (data: QaStreamCitationData) => void
    onDone?: (data: { answer_id: string }) => void
    onError?: (message: string) => void
  },
): void {
  for (const frame of frames) {
    const parsed = parseQaStreamEvent(frame.event, JSON.stringify(frame.data))
    if (!parsed) continue
    if (parsed.type === 'message') handlers.onMessage?.(parsed.data)
    if (parsed.type === 'citation') handlers.onCitation?.(parsed.data)
    if (parsed.type === 'done') handlers.onDone?.(parsed.data)
    if (parsed.type === 'error') handlers.onError?.(parsed.data.message)
  }
}

const readyDetail: PaperDetail = {
  paper_id: 'hss-001',
  title: '联调论文',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
  updated_at: '2026-05-19T11:00:00Z',
}

const routeStubs = {
  'el-table': { template: '<div><slot /></div>' },
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<select class="patrol-select-e14" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  'el-option': true,
  'el-input': {
    props: ['modelValue', 'disabled'],
    template:
      '<textarea class="detail-qa__input" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-space': { template: '<div><slot /></div>' },
  'el-icon': true,
  'el-button': {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-alert': {
    inheritAttrs: false,
    props: ['title', 'description', 'type'],
    template:
      '<div class="el-alert-stub" v-bind="$attrs" :data-title="title" :data-description="description"><slot /></div>',
  },
  RouterLink: true,
  EmptyState,
  PaperGraph: paperGraphSmokeStub,
  PaperMetadataCard: { template: '<div />' },
  PaperStatusPanel: { template: '<div class="status-panel" />' },
  GraphToolbar: {
    props: ['disabled'],
    template: '<div class="graph-toolbar" :data-disabled="disabled ? \'true\' : \'false\'" />',
  },
  GraphLegend: { template: '<div />' },
  GraphNodeDrawer: { template: '<div />' },
  InsightCard: {
    props: ['title', 'insightId', 'summary'],
    template:
      '<article class="patrol-insight"><h3>{{ title }}</h3><p class="insight-summary">{{ summary }}</p><slot /></article>',
  },
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: {
    props: ['label', 'nodeId'],
    template: '<button class="citation-tag">{{ label }} ({{ nodeId }})</button>',
  },
}

async function mountAt(path: string) {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(routerViewShell, {
    global: { plugins: [router], stubs: routeStubs },
  })
  await flushPromises()
  return wrapper
}

function mountPaperStatusComposable(paperId: string, intervalMs = 1000) {
  let exposed: ReturnType<typeof usePaperStatus> | undefined
  const Host = defineComponent({
    setup() {
      exposed = usePaperStatus(paperId, intervalMs)
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return { wrapper, api: exposed! }
}

describe('V1 DoD E-11 — empty graph / no-match subgraph QA', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e11' } })
    mockGetPaperStatus.mockResolvedValue(
      statusResponse({
        paper_id: 'hss-001',
        status: 'ready',
        percent: 100,
        stage: 'ready',
        message: '完成',
        updated_at: '2026-05-19T11:00:00Z',
      }),
    )
    mockGetPaperGraph.mockResolvedValue({
      data: { paper_id: 'hss-001', paradigm: 'HSS', nodes: [], edges: [] },
      meta: { request_id: 'e11-empty' },
    })
  })

  it('detail QA with empty-graph mock stream shows answer without 错误: prefix', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: Parameters<typeof dispatchSseFrames>[1]) => {
        dispatchSseFrames(
          [
            { event: 'message', data: { delta: `根据空图谱上下文，${BE_FE_E11_E15.E11.mockDisclaimer}` } },
            { event: 'done', data: { answer_id: 'ans-empty' } },
          ],
          handlers,
        )
        await Promise.resolve()
      },
    )

    const wrapper = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('xyzzy 无匹配')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    const answer = wrapper.find('.detail-qa__answer-text').text()
    expect(answer).toContain(BE_FE_E11_E15.E11.mockDisclaimer)
    expect(answer.startsWith(BE_FE_E11_E15.E11.noErrorPrefix)).toBe(false)
  })
})

describe('V1 DoD E-12 — CLI ASCII contract (paired with BE subprocess)', () => {
  it('run_qa parseQaStreamEvent rejects malformed frames without throwing', () => {
    expect(parseQaStreamEvent('message', '{bad')).toBeNull()
    expect(parseQaStreamEvent('ping', '{}')).toBeNull()
  })
})

describe('V1 DoD E-13 — usePaperStatus unmount stops polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGetPaperStatusForComposable.mockReset()
    mockGetPaperStatusForComposable.mockResolvedValue(statusResponse(processingStatus))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('onUnmounted clears interval so no further status polls', async () => {
    const { wrapper, api } = mountPaperStatusComposable('paper-e13', 1000)

    api.start()
    await flushPromises()
    expect(mockGetPaperStatusForComposable).toHaveBeenCalledTimes(1)

    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    expect(mockGetPaperStatusForComposable).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('PIPELINE_STATUS_UNAVAILABLE rejection stops polling without leaking timers', async () => {
    mockGetPaperStatusForComposable.mockRejectedValue(
      new ApiClientError({ code: BE_FE_E11_E15.E13.statusUnavailable, message: '进度尚未初始化' }, 409),
    )
    const { wrapper, api } = mountPaperStatusComposable('orphan-e13', 1000)

    api.start()
    await flushPromises()

    expect(api.polling.value).toBe(false)
    expect(api.status.value).toBeNull()
    await vi.advanceTimersByTimeAsync(5000)
    expect(mockGetPaperStatusForComposable).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})

describe('V1 DoD E-14 — empty papers list and zero patrol insights', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('papers list EmptyState shows baseline copy when items empty', async () => {
    mockListPapers.mockResolvedValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      meta: { request_id: 'e14-empty' },
    })

    const wrapper = await mountAt('/papers')
    const empty = wrapper.find('.empty-state')
    expect(empty.find('.empty-state__title').text()).toBe(BE_FE_E11_E15.E14.papersEmptyTitle)
    expect(empty.find('.empty-state__body').text()).toBe(BE_FE_E11_E15.E14.papersEmptyBody)
    expect(wrapper.find('.papers').exists()).toBe(true)
  })

  it('PatrolView renders report shell with zero insights without crashing', async () => {
    mockListPapers.mockResolvedValue({
      data: {
        items: [
          { paper_id: 'hss-001', title: 'A', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:00:00Z' },
          { paper_id: 'hss-002', title: 'B', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:10:00Z' },
        ],
        total: 2,
        offset: 0,
        limit: 20,
      },
      meta: { request_id: 'e14-patrol' },
    })
    const emptyReport: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: emptyReport, meta: { request_id: 'ok' } })

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__report').exists()).toBe(true)
    expect(wrapper.text()).toContain(BE_FE_E11_E15.E14.patrolReportTitle)
    expect(wrapper.findAll('.patrol-insight')).toHaveLength(0)
  })
})

describe('V1 DoD E-15 — ApiClientError and global toast on 5xx', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('papers list survives 500 without white screen', async () => {
    mockListPapers.mockRejectedValue(
      new ApiClientError({ code: BE_FE_E11_E15.E15.elMessageCode, message: BE_FE_E11_E15.E15.serverMessage }, 500),
    )

    const wrapper = await mountAt('/papers')
    await flushPromises()

    expect(wrapper.find('.papers').exists()).toBe(true)
  })

  it('ApiClientError preserves code and statusCode for upstream failures', () => {
    const err = new ApiClientError(
      { code: BE_FE_E11_E15.E15.elMessageCode, message: BE_FE_E11_E15.E15.serverMessage },
      503,
    )
    expect(err.code).toBe('SERVER')
    expect(err.statusCode).toBe(503)
    expect(err.message).toBe(BE_FE_E11_E15.E15.serverMessage)
  })

  it('papers store fetchList records ApiClientError message from 5xx', async () => {
    const { usePaperStore } = await import('@/stores/paper')
    mockListPapers.mockRejectedValue(
      new ApiClientError({ code: BE_FE_E11_E15.E15.elMessageCode, message: BE_FE_E11_E15.E15.serverMessage }, 500),
    )
    setActivePinia(createPinia())
    const store = usePaperStore()
    await expect(store.fetchList()).rejects.toBeInstanceOf(ApiClientError)
    expect(store.lastError).toBe(BE_FE_E11_E15.E15.serverMessage)
  })
})
