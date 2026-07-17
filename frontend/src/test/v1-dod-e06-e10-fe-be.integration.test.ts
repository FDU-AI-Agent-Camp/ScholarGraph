/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD §6.5 E-06～E-10 — 边界鲁棒性前后端联调联试（FE 侧）.
 *
 * 与 tests/integration/test_dod_e06_e10_fe_be.py 成对验收。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { PaperDetail, PatrolReport, QaStreamCitationData } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { statusResponse } from '@/test/fixtures/paperStatus'
import { appendUniqueCitation } from '@/utils/paperGraph'
import { formatPatrolError, resolvePatrolApiError } from '@/utils/patrolForm'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'

/** BE error code / 行为 → FE 展示（§6.5 E-06～E-10）. */
const BE_FE_E06_E10 = {
  E06: {
    graphNotReady: PATROL_BASELINE_COPY.graphNotReadyTitle,
    insufficient: PATROL_BASELINE_COPY.insufficientDataTitle,
  },
  E07: { errorPrefix: '错误:', malformedJsonReturnsNull: true },
  E08: { qaStreamSnippet: 'LLM connection refused' },
  E09: { dedupKey: 'n1' },
  E10: {
    mockPatrolPrefix: '【Mock 巡检摘要】',
    mockDisclaimer: '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）',
    templateSummaryHint: '分析视角',
  },
} as const

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
      '<select class="patrol-select-e06" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
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
    props: ['title', 'insightId', 'summary'],
    template:
      '<article class="patrol-insight" :data-id="insightId"><h3>{{ title }}</h3><p class="insight-summary">{{ summary }}</p><slot /></article>',
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

describe('V1 DoD E-06 — patrol graph missing / insufficient nodes', () => {
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
      meta: { request_id: 'e06' },
    })
  })

  it('formatPatrolError maps GRAPH_NOT_READY to baseline (BE 409)', () => {
    const text = formatPatrolError('GRAPH_NOT_READY', '图谱未就绪')
    expect(text).toContain(BE_FE_E06_E10.E06.graphNotReady)
  })

  it('formatPatrolError maps PATROL_INSUFFICIENT_DATA to baseline (BE 422)', () => {
    const text = formatPatrolError('PATROL_INSUFFICIENT_DATA', '缺少 AnalyticalLens')
    expect(text).toContain(BE_FE_E06_E10.E06.insufficient)
  })

  it('PatrolView shows GRAPH_NOT_READY panel on BE 409 without white screen', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view').exists()).toBe(true)
    const alert = wrapper.find('.patrol-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(BE_FE_E06_E10.E06.graphNotReady)
  })

  it('PatrolView shows PATROL_INSUFFICIENT_DATA panel on BE 422', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '缺少 Thesis 节点' }, 422),
    )

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const fe = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '缺少 Thesis 节点')
    expect(wrapper.find('.patrol-view__error-panel .el-alert-stub').attributes('data-title')).toBe(fe.title)
    expect(fe.title).toBe(BE_FE_E06_E10.E06.insufficient)
  })
})

describe('V1 DoD E-07/E-08 — QA SSE disconnect and error events', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e07' } })
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
      meta: { request_id: 'e07-graph' },
    })
  })

  it('E-07: malformed SSE JSON returns null (parser does not throw)', () => {
    expect(parseQaStreamEvent('message', '{bad json')).toBeNull()
    expect(BE_FE_E06_E10.E07.malformedJsonReturnsNull).toBe(true)
  })

  it('E-07: connection reset surfaces as 错误: … in answer area (no white screen)', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: { onError?: (msg: string) => void }) => {
        handlers.onError?.('connection reset')
      },
    )

    const wrapper = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('测试')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    expect(wrapper.find('.detail-qa__answer-text').text()).toBe(`${BE_FE_E06_E10.E07.errorPrefix} connection reset`)
  })

  it('E-08: QA_STREAM_ERROR SSE error event shows backend message in answer area', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: Parameters<typeof dispatchSseFrames>[1]) => {
        dispatchSseFrames(
          [{ event: 'error', data: { code: 'QA_STREAM_ERROR', message: BE_FE_E06_E10.E08.qaStreamSnippet } }],
          handlers,
        )
        await Promise.resolve()
      },
    )

    const wrapper = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('会失败吗')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.detail-qa__answer-text').text()).toContain(BE_FE_E06_E10.E08.qaStreamSnippet)
  })

  it('E-08: GRAPH_NOT_FOUND error frame maps to readable prefix', () => {
    const parsed = parseQaStreamEvent(
      'error',
      JSON.stringify({ code: 'GRAPH_NOT_FOUND', message: '论文 hss-001 的图谱尚未建好' }),
    )
    expect(parsed?.type).toBe('error')
    if (parsed?.type === 'error') {
      expect(`${BE_FE_E06_E10.E07.errorPrefix} ${parsed.data.message}`).toContain('图谱尚未建好')
    }
  })
})

describe('V1 DoD E-09 — citation dedup and empty node_id', () => {
  it('appendUniqueCitation deduplicates repeated SSE citation frames', () => {
    const cite: QaStreamCitationData = {
      type: 'node',
      paper_id: 'hss-001',
      node_id: BE_FE_E06_E10.E09.dedupKey,
      label: '核心论点',
    }
    const once = appendUniqueCitation([], cite)
    const twice = appendUniqueCitation(once, cite)
    expect(twice).toHaveLength(1)
  })

  it('empty node_id citation does not crash dedup keying', () => {
    const empty: QaStreamCitationData = { type: 'node', paper_id: 'hss-001', node_id: '', label: '' }
    const list = appendUniqueCitation([], empty)
    expect(list).toHaveLength(1)
    expect(appendUniqueCitation(list, empty)).toHaveLength(1)
  })

  it('detail accumulates unique citations from duplicate SSE frames', async () => {
    const thesis = graphFixture.data.nodes.find((node) => node.id === 'n1')
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e09' } })
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
    mockGetPaperGraph.mockResolvedValue({ data: graphFixture.data, meta: { request_id: 'e09-g' } })

    const cite = { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: thesis?.label ?? '核心论点' }
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: Parameters<typeof dispatchSseFrames>[1]) => {
        dispatchSseFrames(
          [
            { event: 'message', data: { delta: '见引用' } },
            { event: 'citation', data: cite },
            { event: 'citation', data: cite },
            { event: 'done', data: { answer_id: 'ans-dup' } },
          ],
          handlers,
        )
        await Promise.resolve()
      },
    )

    const wrapper = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('重复 citation')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.citation-tag')).toHaveLength(1)
  })
})

describe('V1 DoD E-10 — LLM failure / mock disclaimer (FE presentation)', () => {
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
      meta: { request_id: 'e10' },
    })
  })

  it('PatrolView renders mock summary with disclaimer (BE mock mode contract)', async () => {
    const mockReport: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [
        {
          insight_id: 'ins-1',
          title: '理论视角冲突',
          summary: `${BE_FE_E06_E10.E10.mockPatrolPrefix}摘要。${BE_FE_E06_E10.E10.mockDisclaimer}`,
          status: 'ready',
          paper_ids: ['hss-001', 'hss-002'],
          node_refs: [],
        },
      ],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: mockReport, meta: { request_id: 'ok' } })

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const summary = wrapper.find('.insight-summary').text()
    expect(summary).toContain(BE_FE_E06_E10.E10.mockDisclaimer)
  })

  it('PatrolView renders template fallback summary without crashing (BE LLM None)', async () => {
    const templateReport: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [
        {
          insight_id: 'ins-tpl',
          title: '理论视角冲突',
          summary: `《消费社会》与《公共领域》在${BE_FE_E06_E10.E10.templateSummaryHint}上存在张力。`,
          status: 'ready',
          paper_ids: ['hss-001', 'hss-002'],
          node_refs: [],
        },
      ],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: templateReport, meta: { request_id: 'tpl' } })

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__report').exists()).toBe(true)
    expect(wrapper.find('.insight-summary').text()).toContain(BE_FE_E06_E10.E10.templateSummaryHint)
  })

  it('QA error path shows message instead of empty answer (BE QA_STREAM_ERROR)', async () => {
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e10-qa' } })
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
    mockGetPaperGraph.mockResolvedValue({ data: graphFixture.data, meta: { request_id: 'e10-g' } })
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: Parameters<typeof dispatchSseFrames>[1]) => {
        dispatchSseFrames([{ event: 'error', data: { code: 'QA_STREAM_ERROR', message: '模型调用超时' } }], handlers)
        await Promise.resolve()
      },
    )

    const wrapper = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('超时测试')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    const answer = wrapper.find('.detail-qa__answer-text').text()
    expect(answer.length).toBeGreaterThan(0)
    expect(answer).toContain('模型调用超时')
  })

  it('QA live auth failure surfaces QA_STREAM_ERROR message (E-10 invalid Key)', async () => {
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e10-auth' } })
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
    mockGetPaperGraph.mockResolvedValue({ data: graphFixture.data, meta: { request_id: 'e10-auth-g' } })
    mockStreamPaperQa.mockImplementation(
      async (_id: string, _q: string, handlers: Parameters<typeof dispatchSseFrames>[1]) => {
        dispatchSseFrames(
          [
            {
              event: 'error',
              data: {
                code: 'QA_STREAM_ERROR',
                message: 'Error code: 401 - Invalid authorization header.',
              },
            },
          ],
          handlers,
        )
        await Promise.resolve()
      },
    )

    const wrapper = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('鉴权失败测试')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    const answer = wrapper.find('.detail-qa__answer-text').text()
    expect(answer).toMatch(/错误:/)
    expect(answer).toContain('401')
  })
})

describe('V1 DoD E-01～E-05 — regression smoke (paired with e01-e05 files)', () => {
  it('E-02: detail shell survives PAPER_NOT_FOUND', async () => {
    mockGetPaper.mockRejectedValue(new ApiClientError({ code: 'PAPER_NOT_FOUND', message: '论文不存在' }, 404))

    const wrapper = await mountAt('/papers/ghost-e06')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
  })
})
