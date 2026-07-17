/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD §6.5 E-01～E-05 — 边界鲁棒性前后端联调联试（FE 侧）.
 *
 * 与 tests/integration/test_dod_e01_e05_fe_be.py 成对验收。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import type { DataResponse, PaperDetail, PaperStatusData, PatrolReport } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import { elUploadStub } from '@/test/helpers/elUploadStub'
import { uploadNonPdfStub } from '@/test/helpers/uploadNonPdfStub'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { validatePatrolPaperIds, validatePatrolSelection, resolvePatrolApiError } from '@/utils/patrolForm'

import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'

/** BE error code → FE baseline / 行为（§6.5 E-01～E-05）. */
const BE_FE_E_MAP = {
  E01: { code: 'GRAPH_NOT_READY', graphTitle: GRAPH_BASELINE_COPY.graphNotReadyTitle },
  E02: { code: 'PAPER_NOT_FOUND', survivesDetailShell: true },
  E03: { code: 'INGEST_FAILED', clientNonPdfWarning: PAPERS_BASELINE_COPY.nonPdfWarning },
  E04: { failedErrorCode: 'LLM_JSON_INVALID', notReadyTitle: DETAIL_BASELINE_COPY.notReadyAlert },
  E05: { validationTwo: PATROL_BASELINE_COPY.validationExactTwo },
} as const

const mockListPapers = vi.hoisted(() => vi.fn())
const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())
const mockGetPaperStatus = vi.hoisted(() => vi.fn())
const mockUploadPaper = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())
const elMessageWarning = vi.hoisted(() => vi.fn())
const elMessageError = vi.hoisted(() => vi.fn())
const elMessageSuccess = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
  getPaperStatus: (...args: unknown[]) => mockGetPaperStatus(...args),
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('@/api/patrol', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/patrol')>()
  return {
    ...actual,
    runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: unknown[]) => elMessageSuccess(...args),
    warning: (...args: unknown[]) => elMessageWarning(...args),
    error: (...args: unknown[]) => elMessageError(...args),
  },
}))

const readyDetail: PaperDetail = {
  paper_id: 'hss-001',
  title: '联调论文',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
  updated_at: '2026-05-19T11:00:00Z',
}

const failedStatusResponse = failedStatusEnvelope as DataResponse<PaperStatusData>

const routeStubs = {
  'el-table': { template: '<div><slot /></div>' },
  'el-table-column': true,
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<select class="patrol-select-e05" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
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
  PaperGraph: paperGraphSmokeStub,
  PaperMetadataCard: { template: '<div />' },
  PaperStatusPanel: {
    template: '<div class="status-panel-stub" />',
  },
  GraphToolbar: {
    props: ['disabled'],
    template: '<div class="graph-toolbar" :data-disabled="disabled ? \'true\' : \'false\'" />',
  },
  GraphLegend: { template: '<div />' },
  GraphNodeDrawer: { template: '<div />' },
  InsightCard: true,
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: true,
  RouterLink: true,
  EmptyState: { template: '<div />' },
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

describe('V1 DoD E-01 — graph GRAPH_NOT_READY ↔ FE graph copy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({
      data: { ...readyDetail, paper_id: 'hss-002', status: 'processing' },
      meta: { request_id: 'e01' },
    })
    mockGetPaperGraph.mockRejectedValue(
      new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱尚未就绪，请轮询 status' }, 409),
    )
  })

  it('E-01 red: graph view shows baseline title and disables toolbar', async () => {
    const wrapper = await mountAt('/papers/hss-002/graph')
    await flushPromises()

    const alert = wrapper.find('.graph-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(BE_FE_E_MAP.E01.graphTitle)
    expect(wrapper.find('.graph-toolbar').attributes('data-disabled')).toBe('true')
  })

  it('E-01 green: ready graph loads smoke stub without error panel', async () => {
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'e01-ok' } })
    mockGetPaperGraph.mockResolvedValue({
      data: graphFixture.data,
      meta: { request_id: 'e01-graph' },
    })

    const wrapper = await mountAt('/papers/hss-001/graph')
    await flushPromises()

    expect(wrapper.find('.graph-view__error-panel').exists()).toBe(false)
    expect(wrapper.find('.paper-graph-smoke-stub').exists()).toBe(true)
  })
})

describe('V1 DoD E-02 — PAPER_NOT_FOUND detail shell', () => {
  it('E-02 red: detail survives 404 without white screen', async () => {
    mockGetPaper.mockRejectedValue(new ApiClientError({ code: 'PAPER_NOT_FOUND', message: '论文不存在: ghost' }, 404))

    const wrapper = await mountAt('/papers/ghost')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    expect(BE_FE_E_MAP.E02.survivesDetailShell).toBe(true)
    expect(wrapper.find('.detail-header').exists()).toBe(false)
  })
})

describe('V1 DoD E-03 — upload INGEST_FAILED and client non-PDF guard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListPapers.mockResolvedValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      meta: { request_id: 'e03' },
    })
  })

  it('E-03 red: BE INGEST_FAILED shows inline alert with API message', async () => {
    mockUploadPaper.mockRejectedValue(
      new ApiClientError({ code: 'INGEST_FAILED', message: '无法解析 PDF 或文件已损坏' }, 400),
    )

    const wrapper = await mountAt('/papers')
    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.paper-upload__error')
    expect(alert.attributes('data-title')).toBe('INGEST_FAILED')
    expect(wrapper.find('.paper-upload__error-message').text()).toContain('无法解析 PDF')
    expect(elMessageError).not.toHaveBeenCalled()
  })

  it('E-03 boundary: non-PDF filename blocked client-side with warning', async () => {
    setActivePinia(createPinia())
    const PaperUpload = (await import('@/components/papers/PaperUpload.vue')).default

    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          'el-upload': uploadNonPdfStub,
          'el-alert': routeStubs['el-alert'],
          'el-button': routeStubs['el-button'],
          'el-icon': true,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    expect(elMessageWarning).toHaveBeenCalledWith(BE_FE_E_MAP.E03.clientNonPdfWarning)
    expect(mockUploadPaper).not.toHaveBeenCalled()
  })
})

describe('V1 DoD E-04 — failed pipeline status and detail QA guard', () => {
  it('E-04: status panel shows error_code and failed_during from fixture', async () => {
    mockGetPaperStatus.mockResolvedValue(failedStatusResponse)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-failed-001', autoStart: true },
      global: {
        stubs: {
          'el-progress': true,
          'el-alert': routeStubs['el-alert'],
          'el-button': routeStubs['el-button'],
        },
      },
    })
    await flushPromises()

    const alert = wrapper.find('.el-alert-stub')
    expect(alert.attributes('data-title')).toBe(BE_FE_E_MAP.E04.failedErrorCode)
    expect(alert.attributes('data-description')).toBe(failedStatusResponse.data.message)
    expect(wrapper.text()).toContain('classifying')
  })

  it('E-04: detail disables QA with notReady alert when paper status is failed', async () => {
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
    mockGetPaperStatus.mockResolvedValue(failedStatusResponse)

    const wrapper = await mountAt('/papers/hss-failed-001')
    await flushPromises()

    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(BE_FE_E_MAP.E04.notReadyTitle)
    expect(wrapper.find('.detail-qa__input').attributes('disabled')).toBeDefined()
  })
})

describe('V1 DoD E-05 — patrol paper_ids validation', () => {
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
      meta: { request_id: 'e05' },
    })
  })

  it('E-05 boundary: client rejects 1 or 3 paper ids before API', () => {
    expect(validatePatrolPaperIds(['hss-001'])).toBe(BE_FE_E_MAP.E05.validationTwo)
    expect(validatePatrolPaperIds(['hss-001', 'hss-002', 'hss-003'])).toBe(BE_FE_E_MAP.E05.validationTwo)
    expect(validatePatrolSelection('', 'hss-002')).toBe(BE_FE_E_MAP.E05.validationTwo)
  })

  it('E-05 red: PatrolView shows validation alert without calling runPatrol', async () => {
    const wrapper = await mountAt('/patrol')
    const selects = wrapper.findAll('.patrol-select-e05')
    await selects[0]?.setValue('hss-001')
    await selects[1]?.setValue('')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__alert').attributes('data-title')).toBe(BE_FE_E_MAP.E05.validationTwo)
    expect(mockRunPatrol).not.toHaveBeenCalled()
  })

  it('E-05 green: exactly two papers invokes runPatrol', async () => {
    const report: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: report, meta: { request_id: 'ok' } })

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['hss-001', 'hss-002'], { mode: 'lens_clash' })
  })

  it('E-05 red: BE 422 PATROL_INSUFFICIENT maps to baseline (contrast with count validation)', () => {
    const fe = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
    expect(fe.title).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(fe.title).not.toBe(BE_FE_E_MAP.E05.validationTwo)
  })
})

describe('V1 DoD E-01～E-05 — OpenAPI / fixture contract', () => {
  it('failed status fixture aligns with BE E-04 fields', () => {
    expect(failedStatusResponse.data.error_code).toBe('LLM_JSON_INVALID')
    expect(failedStatusResponse.data.failed_during).toBe('classifying')
    expect(failedStatusResponse.data.status).toBe('failed')
  })
})
