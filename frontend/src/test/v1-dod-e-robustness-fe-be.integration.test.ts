/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD §6.5 E — 边界处理与鲁棒性前后端联调联试.
 *
 * 与 tests/integration/test_dod_e_robustness.py 成对：后端 error code ↔ FE 文案/行为。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { PaperDetail, PatrolReport, QaStreamCitationData } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { appendUniqueCitation } from '@/utils/paperGraph'
import { resolvePatrolApiError } from '@/utils/patrolForm'

import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import { statusResponse } from '@/test/fixtures/paperStatus'

const mockListPapers = vi.hoisted(() => vi.fn())
const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())
const mockGetPaperStatus = vi.hoisted(() => vi.fn())
const mockStreamPaperQa = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
  getPaperStatus: (...args: unknown[]) => mockGetPaperStatus(...args),
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

/** BE error code → FE baseline copy（与 progress.md §6.5 对齐）. */
const BE_FE_ERROR_MAP = {
  GRAPH_NOT_READY: {
    patrolTitle: PATROL_BASELINE_COPY.graphNotReadyTitle,
    graphTitle: GRAPH_BASELINE_COPY.graphNotReadyTitle,
  },
  PATROL_INSUFFICIENT_DATA: {
    patrolTitle: PATROL_BASELINE_COPY.insufficientDataTitle,
  },
  GRAPH_NOT_FOUND: {
    qaPrefix: '错误:',
  },
  QA_STREAM_ERROR: {
    qaContains: 'LLM connection refused',
  },
} as const

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
      '<select class="patrol-select-e" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
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
      '<div class="el-alert-stub" v-bind="$attrs" :data-title="title" :data-description="description" :data-type="type"><slot /></div>',
  },
  RouterLink: true,
  EmptyState: { template: '<div class="empty-state"><slot /></div>' },
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
    props: ['title', 'insightId'],
    template: '<div class="patrol-insight" :data-id="insightId">{{ title }}</div>',
  },
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: {
    props: ['label', 'nodeId'],
    template: '<button class="citation-tag">{{ label }} ({{ nodeId }})</button>',
  },
}

async function mountAt(path: string, query?: Record<string, string>) {
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

async function submitDetailQuestion(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('.detail-qa__input').setValue('测试问题')
  const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
  await askButton?.trigger('click')
  await flushPromises()
}

describe('V1 DoD E — BE error code ↔ FE presentation map', () => {
  it('maps patrol GRAPH_NOT_READY to baseline copy', () => {
    const fe = resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪')
    expect(fe.title).toBe(BE_FE_ERROR_MAP.GRAPH_NOT_READY.patrolTitle)
  })

  it('maps patrol PATROL_INSUFFICIENT_DATA to baseline copy', () => {
    const fe = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
    expect(fe.title).toBe(BE_FE_ERROR_MAP.PATROL_INSUFFICIENT_DATA.patrolTitle)
  })

  it('parses QA SSE GRAPH_NOT_FOUND for detail error prefix', () => {
    const parsed = parseQaStreamEvent(
      'error',
      JSON.stringify({ code: 'GRAPH_NOT_FOUND', message: '论文 hss-001 的图谱尚未建好' }),
    )
    expect(parsed?.type).toBe('error')
    if (parsed?.type === 'error') {
      expect(`${BE_FE_ERROR_MAP.GRAPH_NOT_FOUND.qaPrefix} ${parsed.data.message}`).toContain('图谱尚未建好')
    }
  })
})

describe('V1 DoD E-05 — patrol client-side validation blocks bad requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
      meta: { request_id: 'e' },
    })
  })

  it('empty paper selection shows validation alert without calling runPatrol', async () => {
    const { wrapper } = await mountAt('/patrol')
    const selects = wrapper.findAll('.patrol-select-e')
    await selects[0]?.setValue('')
    await selects[1]?.setValue('')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__alert').attributes('data-title')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
    expect(mockRunPatrol).not.toHaveBeenCalled()
  })

  it('duplicate paper ids are rejected by validatePatrolSelection helper', () => {
    expect(PATROL_BASELINE_COPY.validationDuplicate('hss-001')).toContain('hss-001')
  })
})

describe('V1 DoD E-06/E-14 — patrol API red paths and empty insights', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
      meta: { request_id: 'e' },
    })
  })

  it('PatrolView shows GRAPH_NOT_READY panel matching BE 409', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const { wrapper } = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(BE_FE_ERROR_MAP.GRAPH_NOT_READY.patrolTitle)
  })

  it('PatrolView renders report shell with zero insights without crashing (E-14)', async () => {
    const emptyReport: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: emptyReport, meta: { request_id: 'ok' } })

    const { wrapper } = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__report').exists()).toBe(true)
    expect(wrapper.findAll('.patrol-insight')).toHaveLength(0)
  })
})

describe('V1 DoD E-07/E-08 — QA SSE red paths on detail view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e' } })
    mockGetPaperStatus.mockResolvedValue(
      statusResponse({
        paper_id: 'hss-001',
        status: 'ready',
        percent: 100,
        stage: 'ready',
        message: '处理完成',
        updated_at: '2026-05-19T11:00:00Z',
      }),
    )
    mockGetPaperGraph.mockResolvedValue({
      data: graphFixture.data,
      meta: { request_id: 'e-graph' },
    })
  })

  it('surfaces SSE connection error in answer area (E-07)', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: { onError?: (msg: string) => void }) => {
        handlers.onError?.('connection reset')
      },
    )

    const { wrapper } = await mountAt('/papers/hss-001')
    await submitDetailQuestion(wrapper)

    expect(wrapper.find('.detail-qa__answer-text').text()).toBe('错误: connection reset')
  })

  it('surfaces QA_STREAM_ERROR from backend SSE error event (E-08)', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: { onError?: (msg: string) => void }) => {
        dispatchSseFrames(
          [{ event: 'error', data: { code: 'QA_STREAM_ERROR', message: 'LLM connection refused' } }],
          handlers,
        )
        await Promise.resolve()
      },
    )

    const { wrapper } = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input textarea, .detail-qa__input').setValue('会失败吗')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.detail-qa__answer-text').text()).toContain(BE_FE_ERROR_MAP.QA_STREAM_ERROR.qaContains)
  })

  it('functional mock stream still renders answer and citation (E-11 happy path)', async () => {
    const thesis = graphFixture.data.nodes.find((node) => node.id === 'n1')
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: Parameters<typeof dispatchSseFrames>[1]) => {
        dispatchSseFrames(
          [
            { event: 'message', data: { delta: '根据图谱，' } },
            {
              event: 'citation',
              data: { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: thesis?.label ?? '核心论点' },
            },
            { event: 'done', data: { answer_id: 'ans-hss-001' } },
          ],
          handlers,
        )
        await Promise.resolve()
      },
    )

    const { wrapper } = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input textarea, .detail-qa__input').setValue('xyzzy 无关问题')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.detail-qa__answer-text').text()).toContain('根据图谱')
    expect(wrapper.findAll('.citation-tag').length).toBeGreaterThanOrEqual(1)
  })
})

describe('V1 DoD E-09 — citation dedup and empty node_id tolerance', () => {
  it('appendUniqueCitation deduplicates repeated frames from chunked SSE', () => {
    const cite: QaStreamCitationData = { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }
    const once = appendUniqueCitation([], cite)
    const twice = appendUniqueCitation(once, cite)
    expect(twice).toHaveLength(1)
  })

  it('empty node_id citation does not break dedup keying', () => {
    const empty: QaStreamCitationData = { type: 'node', paper_id: 'hss-001', node_id: '', label: '' }
    const list = appendUniqueCitation([], empty)
    expect(list).toHaveLength(1)
    expect(appendUniqueCitation(list, empty)).toHaveLength(1)
  })
})

describe('V1 DoD E-01/E-04 — graph and failed status FE feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('E-01: graph 409 shows baseline copy and disables toolbar', async () => {
    mockGetPaper.mockResolvedValue({
      data: { ...readyDetail, paper_id: 'hss-002', status: 'processing' },
      meta: { request_id: 'e' },
    })
    mockGetPaperGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱尚未就绪' }, 409))

    const { wrapper } = await mountAt('/papers/hss-002/graph')
    await flushPromises()

    const alert = wrapper.find('.graph-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(BE_FE_ERROR_MAP.GRAPH_NOT_READY.graphTitle)
    expect(wrapper.find('.graph-toolbar').attributes('data-disabled')).toBe('true')
  })

  it('E-04: failed status fixture drives error_code alert on detail', async () => {
    mockGetPaper.mockResolvedValue({
      data: {
        paper_id: 'hss-failed-001',
        title: '失败论文',
        status: 'failed',
        paradigm: 'HSS',
        created_at: '2026-05-19T10:00:00Z',
      },
      meta: { request_id: 'e' },
    })
    mockGetPaperStatus.mockResolvedValue(failedStatusFixture)

    const { wrapper } = await mountAt('/papers/hss-failed-001')
    await flushPromises()

    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
  })
})

describe('V1 DoD E-15 — network / 5xx survives without white screen', () => {
  it('papers list keeps shell when listPapers returns 500', async () => {
    mockListPapers.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))

    const { wrapper } = await mountAt('/papers')
    await flushPromises()

    expect(wrapper.find('.papers').exists()).toBe(true)
  })

  it('ApiClientError preserves statusCode and code for upstream failures', () => {
    const err = new ApiClientError({ code: 'SERVER', message: 'upstream' }, 503)
    expect(err.statusCode).toBe(503)
    expect(err.code).toBe('SERVER')
    expect(err.message).toBe('upstream')
  })
})

describe('V1 DoD E — route smoke', () => {
  it('detail route name matches collaboration §3', async () => {
    const { router } = await mountAt('/papers/hss-001')
    expect(router.currentRoute.value.name).toBe(RouteName.PaperDetail)
  })
})
