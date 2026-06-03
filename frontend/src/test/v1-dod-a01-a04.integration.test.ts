/**
 * V1 Definition of Done — A-01～A-04（progress.md §6.1）
 *
 * A-01 六主屏 + 路由 ↔ collaboration.md §3 REST 索引
 * A-02 文献库列表 + PDF 上传 → POST /papers
 * A-03 详情 status 轮询（2s）+ ready / failed / processing 三态
 * A-04 图谱 G6 页 + ?node= 高亮 + 409 未就绪提示
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { DataResponse, PaperDetail, PaperStatusData, PaperSummary, UnifiedPaperGraph } from '@/api/types'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { readFrontendSource } from '@/test/helpers/designTokens'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import { statusResponse, readyStatus } from '@/test/fixtures/paperStatus'

import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import processingStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-002.json'

const mockListPapers = vi.hoisted(() => vi.fn())
const mockGetPaper = vi.hoisted(() => vi.fn())
const mockGetPaperGraph = vi.hoisted(() => vi.fn())
const mockGetPaperStatus = vi.hoisted(() => vi.fn())
const mockUploadPaper = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())
const mockStreamPaperQa = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
  getPaperStatus: (...args: unknown[]) => mockGetPaperStatus(...args),
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: (...args: unknown[]) => mockStreamPaperQa(...args),
}))

/** collaboration.md §3.2 REST 端点 ↔ 主屏映射（QA 内嵌于详情，无独立路由） */
const V1_SCREEN_API_MAP = [
  { screen: '工作台', path: '/', routeName: RouteName.Home, rest: [] as string[] },
  { screen: '文献库', path: '/papers', routeName: RouteName.Papers, rest: ['GET /papers', 'POST /papers'] },
  {
    screen: '论文详情',
    path: '/papers/:paperId',
    routeName: RouteName.PaperDetail,
    rest: ['GET /papers/{paper_id}', 'GET /papers/{paper_id}/status'],
  },
  {
    screen: '多尺度问答',
    path: '/papers/:paperId',
    routeName: RouteName.PaperDetail,
    embedded: true,
    rest: ['POST /papers/{paper_id}/qa/stream'],
  },
  {
    screen: '知识图谱',
    path: '/papers/:paperId/graph',
    routeName: RouteName.PaperGraph,
    rest: ['GET /papers/{paper_id}/graph'],
  },
  { screen: '共同体巡检', path: '/patrol', routeName: RouteName.Patrol, rest: ['GET /papers', 'POST /patrol'] },
] as const

const readySummary: PaperSummary = {
  paper_id: 'hss-001',
  title: 'DoD 验收论文',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
}

const readyDetail: PaperDetail = {
  ...readySummary,
  updated_at: '2026-05-19T11:00:00Z',
}

const sampleGraph: UnifiedPaperGraph = {
  paper_id: 'hss-001',
  paradigm: 'HSS',
  nodes: [
    { id: 'n1', label: '核心论点', type: 'Thesis', data: {} },
    { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
  ],
  edges: [],
}

const failedStatusResponse = failedStatusEnvelope as DataResponse<PaperStatusData>
const processingStatusResponse = processingStatusEnvelope as DataResponse<PaperStatusData>
const hss001ReadyStatus: PaperStatusData = {
  ...readyStatus,
  paper_id: 'hss-001',
  message: '处理完成，可进行问答与图谱浏览',
}

const routeStubs = {
  'el-table': { props: ['data'], template: '<div class="el-table-dod"><slot /></div>' },
  'el-table-column': true,
  'el-select': true,
  'el-option': true,
  'el-input': true,
  'el-space': { template: '<div><slot /></div>' },
  'el-icon': true,
  'el-upload': { template: '<div class="el-upload-dod"><slot /></div>' },
  'el-progress': true,
  'el-alert': {
    props: ['title', 'description', 'type'],
    template:
      '<div class="el-alert-stub" :data-title="title" :data-description="description" :data-type="type"><slot /></div>',
  },
  'el-button': { template: '<button type="button" v-bind="$attrs"><slot /></button>' },
  EmptyState: { template: '<div class="empty-state-dod"><slot /></div>' },
  HomeGraphMock: { template: '<div class="home-graph-mock-dod" />' },
  PaperMetadataCard: { template: '<div class="paper-metadata-dod" />' },
  PaperStatusPanel: { template: '<div class="paper-status-dod" />' },
  GraphToolbar: { template: '<div class="graph-toolbar-dod" />' },
  GraphLegend: { template: '<div class="graph-legend-dod" />' },
  GraphNodeDrawer: { template: '<div class="graph-drawer-dod" />' },
  InsightCard: { template: '<div class="insight-card-dod"><slot /></div>' },
  PaperGraph: paperGraphSmokeStub,
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: true,
}

function seedHappyApiMocks(): void {
  mockListPapers.mockResolvedValue({
    data: { items: [readySummary], total: 1, offset: 0, limit: 20 },
    meta: { request_id: 'dod-list' },
  })
  mockGetPaper.mockResolvedValue({
    data: readyDetail,
    meta: { request_id: 'dod-detail' },
  })
  mockGetPaperGraph.mockResolvedValue({
    data: sampleGraph,
    meta: { request_id: 'dod-graph' },
  })
  mockGetPaperStatus.mockResolvedValue(statusResponse(hss001ReadyStatus))
  mockUploadPaper.mockResolvedValue({
    data: { paper_id: 'hss-new', message: '上传成功' },
    meta: { request_id: 'dod-upload' },
  })
  mockRunPatrol.mockResolvedValue({
    data: {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      generated_at: '2026-05-19T12:00:00Z',
      insights: [],
    },
    meta: { request_id: 'dod-patrol' },
  })
  mockStreamPaperQa.mockResolvedValue(undefined)
}

async function mountRoute(path: string, query?: Record<string, string>) {
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
      stubs: routeStubs,
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('V1 DoD A-01 — 六主屏可访问，路由与 collaboration.md §3 一致', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    seedHappyApiMocks()
  })

  it('defines five route records covering six screens (QA embedded in detail)', () => {
    expect(V1_SCREEN_API_MAP).toHaveLength(6)

    const uniquePaths = new Set(
      V1_SCREEN_API_MAP.filter((entry) => !('embedded' in entry && entry.embedded)).map((entry) => entry.path),
    )
    expect(uniquePaths.size).toBe(5)
    expect(routes.map((route) => route.path).sort()).toEqual([
      '/',
      '/papers',
      '/papers/:paperId',
      '/papers/:paperId/graph',
      '/patrol',
    ])
  })

  it('maps each screen to collaboration §3.2 REST endpoints used by FE modules', () => {
    const detailViewSrc = readFrontendSource('views/PaperDetailView.vue')
    const papersViewSrc = readFrontendSource('views/PapersView.vue')
    const graphViewSrc = readFrontendSource('views/PaperGraphView.vue')
    const patrolViewSrc = readFrontendSource('views/PatrolView.vue')

    expect(papersViewSrc).toContain('fetchList')
    expect(papersViewSrc).toContain('PaperUpload')
    expect(readFrontendSource('components/papers/PaperUpload.vue')).toContain('uploadPaper')
    expect(readFrontendSource('stores/paper.ts')).toContain('listPapers')
    expect(detailViewSrc).toContain('fetchDetail')
    expect(detailViewSrc).toContain('streamPaperQa')
    expect(detailViewSrc).toContain('detail-qa')
    expect(graphViewSrc).toContain('fetchGraph')
    expect(readFrontendSource('stores/paper.ts')).toContain('getPaperGraph')
    expect(patrolViewSrc).toContain('runPatrol')

    const restUsed = V1_SCREEN_API_MAP.flatMap((entry) => entry.rest)
    expect(restUsed).toContain('GET /papers')
    expect(restUsed).toContain('POST /papers')
    expect(restUsed).toContain('POST /papers/{paper_id}/qa/stream')
    expect(restUsed).toContain('GET /papers/{paper_id}/graph')
    expect(restUsed).toContain('POST /patrol')
  })

  it.each([
    ['/', RouteName.Home, '.home-title'],
    ['/papers', RouteName.Papers, '.papers-title'],
    ['/papers/hss-001', RouteName.PaperDetail, '.detail-header__title'],
    ['/papers/hss-001/graph', RouteName.PaperGraph, '.graph-view'],
    ['/patrol', RouteName.Patrol, '.patrol-view__title'],
  ] as const)('mounts %s (%s)', async (path, routeName, selector) => {
    const { wrapper, router } = await mountRoute(path)

    expect(router.currentRoute.value.name).toBe(routeName)
    expect(wrapper.find(selector).exists()).toBe(true)
  })

  it('detail route exposes embedded QA section (sixth screen) without extra route', async () => {
    const { wrapper } = await mountRoute('/papers/hss-001')

    expect(wrapper.find('.detail-qa').exists()).toBe(true)
    expect(wrapper.find('.detail-qa__title').text()).toBe(DETAIL_BASELINE_COPY.qaSectionTitle)
  })
})

describe('V1 DoD A-02 — 文献库列表 + PDF 上传 → POST /papers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    seedHappyApiMocks()
  })

  it('loads paper list on /papers mount via GET /papers', async () => {
    await mountRoute('/papers')

    expect(mockListPapers).toHaveBeenCalled()
  })

  it('PaperUpload invokes uploadPaper which posts multipart to /papers', async () => {
    const uploadSrc = readFrontendSource('components/papers/PaperUpload.vue')

    expect(uploadSrc).toContain('uploadPaper')
    expect(uploadSrc).toContain("emit('uploaded'")
  })
})

describe('V1 DoD A-03 — 详情 status 轮询（2s）+ ready / failed / processing 三态', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('usePaperStatus defaults polling interval to 2000ms', () => {
    const src = readFrontendSource('composables/usePaperStatus.ts')
    expect(src).toMatch(/intervalMs\s*=\s*2000/)
    expect(src).toContain('setInterval')
  })

  it('hss-001 ready — terminal status, no failure alert', async () => {
    mockGetPaperStatus.mockResolvedValue(statusResponse(hss001ReadyStatus))

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-001', autoStart: true },
    })
    await flushPromises()

    expect(mockGetPaperStatus).toHaveBeenCalledWith('hss-001')
    expect(wrapper.find('.el-alert-stub').exists()).toBe(false)
    expect(wrapper.text()).toContain(hss001ReadyStatus.message)
  })

  it('hss-failed-001 failed — surfaces error_code and failed_during from fixture', async () => {
    mockGetPaperStatus.mockResolvedValue(failedStatusResponse)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-failed-001', autoStart: true },
    })
    await flushPromises()

    expect(mockGetPaperStatus).toHaveBeenCalledWith('hss-failed-001')
    const alert = wrapper.find('.el-alert-stub')
    expect(alert.attributes('data-title')).toBe('LLM_JSON_INVALID')
    expect(alert.attributes('data-description')).toBe(failedStatusResponse.data.message)
    expect(wrapper.text()).toContain('classifying')
  })

  it('hss-002 processing — shows refresh caption and stepper without failure alert', async () => {
    mockGetPaperStatus.mockResolvedValue(processingStatusResponse)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-002', autoStart: true },
    })
    await flushPromises()

    expect(mockGetPaperStatus).toHaveBeenCalledWith('hss-002')
    expect(wrapper.find('.el-alert-stub').exists()).toBe(false)
    expect(wrapper.text()).toContain(processingStatusResponse.data.message)
    expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.refreshCaption)
  })

  it('keeps polling on processing status until terminal (2s interval)', async () => {
    vi.useFakeTimers()
    mockGetPaperStatus.mockResolvedValue(processingStatusResponse)

    mount(PaperStatusPanel, {
      props: { paperId: 'hss-002', autoStart: true },
    })
    await flushPromises()
    expect(mockGetPaperStatus).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2000)
    expect(mockGetPaperStatus).toHaveBeenCalledTimes(2)
  })
})

describe('V1 DoD A-04 — 图谱 G6 + ?node= 高亮 + 409 未就绪提示', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    seedHappyApiMocks()
  })

  it('passes ?node= query to PaperGraph highlightNodeId on graph route', async () => {
    const { wrapper } = await mountRoute('/papers/hss-001/graph', { node: 'n1' })

    expect(mockGetPaperGraph).toHaveBeenCalledWith('hss-001')
    expect(wrapper.find('.paper-graph-smoke-stub').attributes('data-highlight')).toBe('n1')
    expect(wrapper.find('.paper-graph-smoke-stub').attributes('data-full-bleed')).toBe('true')
  })

  it('shows GRAPH_NOT_READY guidance when graph API returns 409', async () => {
    mockGetPaperGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const { wrapper } = await mountRoute('/papers/hss-002/graph')

    const alert = wrapper.find('.graph-view__error-panel .el-alert-stub')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-title')).toBe(GRAPH_BASELINE_COPY.graphNotReadyTitle)
    expect(alert.attributes('data-description')).toBe(GRAPH_BASELINE_COPY.graphNotReadyDescription)
    expect(wrapper.find('.graph-view__error-cta').exists()).toBe(true)
    expect(wrapper.text()).toContain(GRAPH_BASELINE_COPY.graphNotReadyCta)
    expect(wrapper.find('.paper-graph-smoke-stub').exists()).toBe(false)
  })

  it('tolerates unknown ?node= without breaking graph route shell', async () => {
    const { wrapper } = await mountRoute('/papers/hss-001/graph', { node: 'ghost-node' })

    expect(wrapper.find('.paper-graph-smoke-stub').attributes('data-highlight')).toBe('ghost-node')
    expect(wrapper.find('.graph-view').exists()).toBe(true)
  })
})
