/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD §6.5 — 前后端联调红灯路径与功能可用性（FE 侧）.
 *
 * 与 tests/integration/test_dod_fe_be_red_paths.py 成对验收。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { PaperDetail, PatrolReport } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { elUploadStub } from '@/test/helpers/elUploadStub'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import EmptyState from '@/components/ui/EmptyState.vue'
import { statusResponse } from '@/test/fixtures/paperStatus'
import { resolvePatrolApiError } from '@/utils/patrolForm'

import ingestFailedEnvelope from '../../../docs/api/fixtures/paper-ingest-failed.json'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'

const MOCK_PATROL_PREFIX = '【Mock 巡检摘要】'
const MOCK_DISCLAIMER = '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）'

const mockListPapers = vi.hoisted(() => vi.fn())
const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())
const mockGetPaperStatus = vi.hoisted(() => vi.fn())
const mockUploadPaper = vi.hoisted(() => vi.fn())
const mockStreamPaperQa = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
  getPaperStatus: (...args: unknown[]) => mockGetPaperStatus(...args),
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: (...args: unknown[]) => mockStreamPaperQa(...args),
}))

vi.mock('@/api/patrol', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/patrol')>()
  return {
    ...actual,
    runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
  }
})

/** BE error code → FE 展示契约（与 api-contract / progress §6.5 对齐）. */
const BE_FE_CONTRACT = {
  INGEST_FAILED: { feShowsCodeAsTitle: true },
  PAPER_NOT_FOUND: { survivesShell: true },
  PATROL_INSUFFICIENT_DATA: { patrolTitle: PATROL_BASELINE_COPY.insufficientDataTitle },
  PIPELINE_STATUS_UNAVAILABLE: { genericApiError: true },
  GRAPH_NOT_READY: { patrolTitle: PATROL_BASELINE_COPY.graphNotReadyTitle },
} as const

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
  'el-table-column': true,
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<select class="patrol-select-febe" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
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
  'el-upload': elUploadStub,
  'el-progress': true,
  RouterLink: true,
  EmptyState,
  PaperGraph: paperGraphSmokeStub,
  PaperMetadataCard: { template: '<div />' },
  PaperStatusPanel: { template: '<div class="status-panel" />' },
  GraphToolbar: { template: '<div />' },
  GraphLegend: { template: '<div />' },
  GraphNodeDrawer: { template: '<div />' },
  InsightCard: {
    props: ['title', 'summary', 'insightId'],
    template:
      '<article class="insight-card-febe"><h3>{{ title }}</h3><p class="insight-summary">{{ summary }}</p></article>',
  },
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: true,
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
  return { wrapper, router }
}

describe('V1 DoD FE↔BE — error code contract map', () => {
  it('maps PATROL_INSUFFICIENT_DATA to baseline insufficient panel', () => {
    const fe = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
    expect(fe.title).toBe(BE_FE_CONTRACT.PATROL_INSUFFICIENT_DATA.patrolTitle)
    expect(fe.ctaKind).toBe('reset-selection')
  })

  it('maps unknown patrol codes to API message title', () => {
    const fe = resolvePatrolApiError('PIPELINE_STATUS_UNAVAILABLE', '进度尚未初始化')
    expect(fe.title).toBe('进度尚未初始化')
  })

  it('ingest fixture exposes INGEST_FAILED for upload UI', () => {
    expect(ingestFailedEnvelope.error.code).toBe('INGEST_FAILED')
    expect(ingestFailedEnvelope.error.message).toBeTruthy()
  })
})

describe('V1 DoD E-03 — upload boundary feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListPapers.mockResolvedValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      meta: { request_id: 'febe-e03' },
    })
  })

  it('surfaces oversized upload INGEST_FAILED with API message inline', async () => {
    mockUploadPaper.mockRejectedValue(new ApiClientError({ code: 'INGEST_FAILED', message: '文件超过 32MB 限制' }, 400))

    const { wrapper } = await mountAt('/papers')
    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.paper-upload__error')
    expect(alert.attributes('data-title')).toBe('INGEST_FAILED')
    expect(alert.text()).toContain('32MB')
    expect(alert.text()).toContain(PAPERS_BASELINE_COPY.uploadRetryHint)
  })
})

describe('V1 DoD E-02 — PAPER_NOT_FOUND detail shell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('detail page survives getPaper 404 without white screen', async () => {
    mockGetPaper.mockRejectedValue(new ApiClientError({ code: 'PAPER_NOT_FOUND', message: '论文不存在: ghost' }, 404))

    const { wrapper } = await mountAt('/papers/ghost')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    expect(BE_FE_CONTRACT.PAPER_NOT_FOUND.survivesShell).toBe(true)
  })
})

describe('V1 DoD E-06 — patrol insufficient data panel', () => {
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
      meta: { request_id: 'febe-e06' },
    })
  })

  it('PatrolView shows PATROL_INSUFFICIENT_DATA baseline copy from BE 422', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '缺少 Thesis 节点' }, 422),
    )

    const { wrapper } = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(BE_FE_CONTRACT.PATROL_INSUFFICIENT_DATA.patrolTitle)
  })
})

describe('V1 DoD E-10 — mock patrol / QA functional feedback', () => {
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
      meta: { request_id: 'febe-e10' },
    })
  })

  it('PatrolView renders mock patrol summary with disclaimer prefix', async () => {
    const mockReport: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [
        {
          insight_id: 'ins-lens-clash-001',
          title: '理论视角冲突（Lens Clash）',
          summary: `${MOCK_PATROL_PREFIX}基于两篇论文的图谱节点差异生成摘要。${MOCK_DISCLAIMER}`,
          status: 'ready',
          paper_ids: ['hss-001', 'hss-002'],
          node_refs: [],
        },
      ],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: mockReport, meta: { request_id: 'ok' } })

    const { wrapper } = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const summary = wrapper.find('.insight-summary').text()
    expect(summary).toContain(MOCK_PATROL_PREFIX)
    expect(summary).toContain(MOCK_DISCLAIMER)
  })
})

describe('V1 DoD E-07 — QA empty question client guard', () => {
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
      data: { paper_id: 'hss-001', paradigm: 'HSS', nodes: [], edges: [] },
      meta: { request_id: 'e07-g' },
    })
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('does not call streamPaperQa when question is whitespace-only', async () => {
    const { wrapper } = await mountAt('/papers/hss-001')
    await wrapper.find('.detail-qa__input').setValue('   ')
    const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
    await askButton?.trigger('click')
    await flushPromises()

    expect(mockStreamPaperQa).not.toHaveBeenCalled()
  })
})

describe('V1 DoD E-04 / E-14 — failed status and empty list', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('E-04: failed status fixture drives notReady alert on detail', async () => {
    mockGetPaper.mockResolvedValue({
      data: {
        paper_id: 'hss-failed-001',
        title: '失败论文',
        status: 'failed',
        paradigm: 'HSS',
        created_at: '2026-05-19T10:00:00Z',
      },
      meta: { request_id: 'e04' },
    })
    mockGetPaperStatus.mockResolvedValue(failedStatusFixture)

    const { wrapper } = await mountAt('/papers/hss-failed-001')
    await flushPromises()

    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
  })

  it('E-14: empty papers list shows EmptyState baseline copy', async () => {
    mockListPapers.mockResolvedValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      meta: { request_id: 'e14' },
    })

    const { wrapper } = await mountAt('/papers')
    await flushPromises()

    const empty = wrapper.find('.empty-state')
    expect(empty.find('.empty-state__title').text()).toBe(PAPERS_BASELINE_COPY.emptyTitle)
    expect(empty.find('.empty-state__body').text()).toBe(PAPERS_BASELINE_COPY.emptyBody)
    expect(empty.text()).toContain(PAPERS_BASELINE_COPY.emptyCta)
  })
})

describe('V1 DoD E-13 — status polling error tolerance', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({
      data: { ...readyDetail, status: 'processing' },
      meta: { request_id: 'e13' },
    })
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('detail keeps shell when status poll returns PIPELINE_STATUS_UNAVAILABLE', async () => {
    mockGetPaperStatus.mockRejectedValue(
      new ApiClientError({ code: 'PIPELINE_STATUS_UNAVAILABLE', message: '进度尚未初始化' }, 409),
    )

    const { wrapper } = await mountAt('/papers/hss-001')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    expect(BE_FE_CONTRACT.PIPELINE_STATUS_UNAVAILABLE.genericApiError).toBe(true)
  })
})
