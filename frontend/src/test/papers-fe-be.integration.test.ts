/**
 * FE↔BE 联调：papers 主路径真实行为 + 红路径 UI 反馈。
 *
 * 覆盖 upload → 详情、status 轮询三态、graph 409/500 差异化反馈。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { DataResponse, PaperDetail, PaperStatusData, PaperSummary } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { elUploadStub } from '@/test/helpers/elUploadStub'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import { statusResponse } from '@/test/fixtures/paperStatus'

import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import processingStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-002.json'
import ingestFailedEnvelope from '../../../docs/api/fixtures/paper-ingest-failed.json'

const mockListPapers = vi.hoisted(() => vi.fn())
const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())
const mockGetPaperStatus = vi.hoisted(() => vi.fn())
const mockUploadPaper = vi.hoisted(() => vi.fn())
const mockStreamPaperQa = vi.hoisted(() => vi.fn())
const elMessageSuccess = vi.hoisted(() => vi.fn())
const elMessageWarning = vi.hoisted(() => vi.fn())
const elMessageError = vi.hoisted(() => vi.fn())

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

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: unknown[]) => elMessageSuccess(...args),
    warning: (...args: unknown[]) => elMessageWarning(...args),
    error: (...args: unknown[]) => elMessageError(...args),
  },
}))

const readySummary: PaperSummary = {
  paper_id: 'hss-001',
  title: '联调论文',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
}

const readyDetail: PaperDetail = {
  ...readySummary,
  updated_at: '2026-05-19T11:00:00Z',
}

const processingDetail: PaperDetail = {
  paper_id: 'hss-002',
  title: '处理中论文',
  paradigm: 'HSS',
  status: 'processing',
  created_at: '2026-05-19T10:00:00Z',
  updated_at: '2026-05-19T10:12:00Z',
}

const failedStatusResponse = failedStatusEnvelope as DataResponse<PaperStatusData>
const processingStatusResponse = processingStatusEnvelope as DataResponse<PaperStatusData>

function buildRouteStubs(includeRealUpload = false) {
  return {
    'el-table': { props: ['data'], template: '<div class="el-table-febe"><slot /></div>' },
    'el-table-column': true,
    'el-select': true,
    'el-option': true,
    'el-input': {
      props: ['disabled', 'modelValue', 'type'],
      template:
        '<textarea class="detail-qa__input" :disabled="disabled" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    },
    'el-space': { template: '<div><slot /></div>' },
    'el-icon': true,
    'el-upload': includeRealUpload ? elUploadStub : { template: '<div class="el-upload-febe"><slot /></div>' },
    'el-progress': true,
    'el-alert': {
      inheritAttrs: false,
      props: ['title', 'description', 'type'],
      template:
        '<div class="el-alert-stub" v-bind="$attrs" :data-title="title" :data-description="description" :data-type="type"><slot /></div>',
    },
    'el-button': {
      inheritAttrs: false,
      template:
        '<button type="button" class="graph-view__error-cta-btn" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
    },
    EmptyState: { template: '<div class="empty-state-febe"><slot /></div>' },
    HomeGraphMock: { template: '<div />' },
    PaperMetadataCard: { template: '<div class="paper-metadata-febe" />' },
    GraphToolbar: {
      props: ['disabled'],
      template: '<div class="graph-toolbar-febe" :data-disabled="disabled ? \'true\' : \'false\'" />',
    },
    GraphLegend: { template: '<div />' },
    GraphNodeDrawer: { template: '<div />' },
    PaperGraph: paperGraphSmokeStub,
    BadgeParadigm: true,
    BadgeStatus: true,
    TagCitation: true,
  }
}

async function mountRoute(path: string, query?: Record<string, string>, includeRealUpload = false) {
  setActivePinia(createPinia())
  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })
  await router.push(query ? { path, query } : path)
  await router.isReady()

  const wrapper = mount(routerViewShell, {
    global: {
      plugins: [router],
      stubs: buildRouteStubs(includeRealUpload),
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('papers FE↔BE — upload flow (POST /papers)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListPapers.mockResolvedValue({
      data: { items: [readySummary], total: 1, offset: 0, limit: 20 },
      meta: { request_id: 'febe-list' },
    })
    mockUploadPaper.mockResolvedValue({
      data: { paper_id: 'upload-new-001', status: 'pending', message: '任务已创建，请轮询 status 接口' },
      meta: { request_id: 'febe-upload' },
    })
    mockGetPaper.mockResolvedValue({
      data: { ...readyDetail, paper_id: 'upload-new-001', status: 'pending', title: 'sample' },
      meta: { request_id: 'febe-detail' },
    })
    mockGetPaperStatus.mockResolvedValue(
      statusResponse({
        paper_id: 'upload-new-001',
        status: 'pending',
        percent: 0,
        stage: null,
        message: '任务已创建，请轮询 status 接口',
        updated_at: '2026-05-19T10:00:00Z',
      }),
    )
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('uploads PDF via PaperUpload, shows success toast, navigates to detail', async () => {
    const { wrapper, router } = await mountRoute('/papers', undefined, true)
    const pushSpy = vi.spyOn(router, 'push')

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(mockUploadPaper).toHaveBeenCalledTimes(1)
    const uploadedFile = mockUploadPaper.mock.calls[0]?.[0] as File
    expect(uploadedFile.name).toBe('sample.pdf')
    expect(elMessageSuccess).toHaveBeenCalledWith(PAPERS_BASELINE_COPY.uploadSuccess)
    expect(pushSpy).toHaveBeenCalledWith({
      name: RouteName.PaperDetail,
      params: { paperId: 'upload-new-001' },
    })
  })

  it('surfaces INGEST_FAILED inline on upload without global navigation', async () => {
    const ingestError = ingestFailedEnvelope as { error: { code: string; message: string } }
    mockUploadPaper.mockRejectedValue(
      new ApiClientError({ code: ingestError.error.code, message: ingestError.error.message }, 400),
    )

    const { wrapper, router } = await mountRoute('/papers', undefined, true)
    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()
    await router.isReady()

    expect(router.currentRoute.value.name).toBe(RouteName.Papers)
    const alert = wrapper.find('.paper-upload__error')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-title')).toBe('INGEST_FAILED')
    expect(alert.text()).toContain(ingestError.error.message)
    expect(alert.text()).toContain(PAPERS_BASELINE_COPY.uploadRetryHint)
  })

  it('refreshes paper list after upload before navigating to detail', async () => {
    const { wrapper } = await mountRoute('/papers', undefined, true)
    const listCallsAfterMount = mockListPapers.mock.calls.length

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(mockListPapers.mock.calls.length).toBeGreaterThan(listCallsAfterMount)
  })

  it('after upload navigates to detail route', async () => {
    const { wrapper, router } = await mountRoute('/papers', undefined, true)
    const pushSpy = vi.spyOn(router, 'push')

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(pushSpy).toHaveBeenCalledWith({
      name: RouteName.PaperDetail,
      params: { paperId: 'upload-new-001' },
    })
  })

  it('uploaded paper detail polls from pending into processing status', async () => {
    vi.useFakeTimers()
    const pendingStatus = statusResponse({
      paper_id: 'upload-new-001',
      status: 'pending',
      percent: 0,
      stage: null,
      message: '已接收 PDF，正在自动解构…',
      updated_at: '2026-05-19T10:00:00Z',
    })
    const processingForUpload = statusResponse({
      ...processingStatusResponse.data,
      paper_id: 'upload-new-001',
    })
    mockGetPaperStatus
      .mockResolvedValueOnce(pendingStatus)
      .mockResolvedValue(processingForUpload)
    mockGetPaper.mockResolvedValue({
      data: {
        paper_id: 'upload-new-001',
        title: 'sample',
        status: 'pending',
        paradigm: 'HSS',
        created_at: '2026-05-19T10:00:00Z',
      },
      meta: { request_id: 'febe-detail-pending' },
    })

    const { wrapper } = await mountRoute('/papers/upload-new-001')
    await flushPromises()

    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(mockGetPaperStatus.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).toContain(processingForUpload.data.message)
    vi.useRealTimers()
  })
})

describe('papers FE↔BE — detail status polling on route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('processing paper disables QA with not-ready alert and polls status', async () => {
    vi.useFakeTimers()
    mockGetPaper.mockResolvedValue({ data: processingDetail, meta: { request_id: 'febe' } })
    mockGetPaperStatus.mockResolvedValue(processingStatusResponse)

    const { wrapper } = await mountRoute('/papers/hss-002')
    await flushPromises()

    expect(mockGetPaperStatus).toHaveBeenCalledWith('hss-002')
    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
    expect(wrapper.find('.detail-qa__input').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain(processingStatusResponse.data.message)

    await vi.advanceTimersByTimeAsync(2000)
    expect(mockGetPaperStatus.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('failed paper shows error_code alert from fixture on status panel', async () => {
    mockGetPaper.mockResolvedValue({
      data: {
        paper_id: 'hss-failed-001',
        title: '失败论文',
        status: 'failed',
        paradigm: 'HSS',
        created_at: '2026-05-19T10:00:00Z',
      },
      meta: { request_id: 'febe' },
    })
    mockGetPaperStatus.mockResolvedValue(failedStatusResponse)

    const { wrapper } = await mountRoute('/papers/hss-failed-001')
    await flushPromises()

    const alert = wrapper.find('.status-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe('LLM_JSON_INVALID')
    expect(alert.attributes('data-description')).toBe(failedStatusResponse.data.message)
    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
  })

  it('ready paper enables QA without not-ready alert', async () => {
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'febe' } })
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
      meta: { request_id: 'febe-graph' },
    })

    const { wrapper } = await mountRoute('/papers/hss-001')
    await flushPromises()

    expect(wrapper.find('.detail-qa__alert').exists()).toBe(false)
    expect(wrapper.find('.detail-qa__input').attributes('disabled')).toBeUndefined()
  })
})

describe('papers FE↔BE — graph red paths and deep-link', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPaper.mockResolvedValue({ data: readyDetail, meta: { request_id: 'febe' } })
    mockGetPaperGraph.mockResolvedValue({
      data: {
        paper_id: 'hss-001',
        paradigm: 'HSS',
        nodes: [{ id: 'n1', label: '核心论点', type: 'Thesis', data: {} }],
        edges: [],
      },
      meta: { request_id: 'febe-graph' },
    })
  })

  it('409 GRAPH_NOT_READY shows baseline copy, disables toolbar, CTA returns to detail', async () => {
    mockGetPaper.mockResolvedValue({ data: processingDetail, meta: { request_id: 'febe' } })
    mockGetPaperGraph.mockRejectedValue(
      new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱尚未就绪，请轮询 status 接口' }, 409),
    )

    const { wrapper, router } = await mountRoute('/papers/hss-002/graph')
    const pushSpy = vi.spyOn(router, 'push')
    await flushPromises()

    const alert = wrapper.find('.graph-view__error-panel .el-alert-stub')
    expect(alert.attributes('data-title')).toBe(GRAPH_BASELINE_COPY.graphNotReadyTitle)
    expect(alert.attributes('data-description')).toBe(GRAPH_BASELINE_COPY.graphNotReadyDescription)
    expect(wrapper.find('.graph-toolbar-febe').attributes('data-disabled')).toBe('true')
    expect(wrapper.find('.paper-graph-smoke-stub').exists()).toBe(false)

    await wrapper.find('.graph-view__error-cta').trigger('click')
    expect(pushSpy).toHaveBeenCalledWith('/papers/hss-002')
  })

  it('passes ?node= to highlight on graph route', async () => {
    const { wrapper } = await mountRoute('/papers/hss-001/graph', { node: 'n1' })
    await flushPromises()

    expect(wrapper.find('.paper-graph-smoke-stub').attributes('data-highlight')).toBe('n1')
  })

  it('tolerates unknown ?node= query without breaking graph shell', async () => {
    const { wrapper } = await mountRoute('/papers/hss-001/graph', { node: 'missing-node' })
    await flushPromises()

    expect(wrapper.find('.paper-graph-smoke-stub').attributes('data-highlight')).toBe('missing-node')
    expect(wrapper.find('.graph-view').exists()).toBe(true)
  })
})

describe('papers FE↔BE — detail 404 and list failure robustness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStreamPaperQa.mockResolvedValue(undefined)
  })

  it('detail survives getPaper 404 without crashing', async () => {
    mockGetPaper.mockRejectedValue(new ApiClientError({ code: 'PAPER_NOT_FOUND', message: '论文不存在: ghost' }, 404))

    const { wrapper } = await mountRoute('/papers/ghost')
    await flushPromises()

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    expect(wrapper.find('.detail-header').exists()).toBe(false)
  })

  it('papers list survives listPapers rejection and keeps page shell', async () => {
    mockListPapers.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))

    const { wrapper } = await mountRoute('/papers')
    await flushPromises()

    expect(wrapper.find('.papers-title').text()).toBe(PAPERS_BASELINE_COPY.title)
    expect(wrapper.find('.papers').exists()).toBe(true)
  })
})
