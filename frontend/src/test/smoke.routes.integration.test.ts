/**
 * 答辩路径冒烟 + 边界鲁棒性：memory router 挂载真实视图，API 层 mock。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { PaperDetail, PaperSummary, UnifiedPaperGraph } from '@/api/types'
import { HOME_BASELINE_COPY } from '@/constants/homeCopy'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { paperGraphSmokeStub } from '@/test/helpers/paperGraphSmokeStub'
import { routerViewShell } from '@/test/helpers/routerViewShell'

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

const readySummary: PaperSummary = {
  paper_id: 'hss-001',
  title: 'Smoke 论文',
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
  nodes: [{ id: 'n1', label: '核心论点', type: 'Thesis', data: {} }],
  edges: [],
}

const routeStubs = {
  'el-table': {
    props: ['data'],
    template: '<div class="el-table-smoke"><slot /></div>',
  },
  'el-table-column': true,
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<input class="patrol-select-smoke" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-option': true,
  'el-input': true,
  'el-space': { template: '<div><slot /></div>' },
  'el-icon': true,
  'el-upload': { template: '<div class="el-upload-smoke"><slot /></div>' },
  'el-progress': true,
  EmptyState: { template: '<div class="empty-state-smoke"><slot /></div>' },
  HomeGraphMock: { template: '<div class="home-graph-mock-smoke" />' },
  PaperMetadataCard: { template: '<div class="paper-metadata-smoke" />' },
  PaperStatusPanel: { template: '<div class="paper-status-smoke" />' },
  GraphToolbar: { template: '<div class="graph-toolbar-smoke" />' },
  GraphLegend: { template: '<div class="graph-legend-smoke" />' },
  GraphNodeDrawer: { template: '<div class="graph-drawer-smoke" />' },
  InsightCard: { template: '<div class="insight-card-smoke"><slot /></div>' },
  PaperGraph: paperGraphSmokeStub,
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: true,
}

function seedHappyApiMocks(): void {
  mockListPapers.mockResolvedValue({
    data: { items: [readySummary], total: 1, offset: 0, limit: 20 },
    meta: { request_id: 'smoke-list' },
  })
  mockGetPaper.mockResolvedValue({
    data: readyDetail,
    meta: { request_id: 'smoke-detail' },
  })
  mockGetPaperGraph.mockResolvedValue({
    data: sampleGraph,
    meta: { request_id: 'smoke-graph' },
  })
  mockGetPaperStatus.mockResolvedValue({
    data: { paper_id: 'hss-001', status: 'ready', stage: 'done', progress: 100 },
    meta: { request_id: 'smoke-status' },
  })
  mockUploadPaper.mockResolvedValue({
    data: { paper_id: 'hss-new', message: '上传成功' },
  })
  mockRunPatrol.mockResolvedValue({
    data: {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      generated_at: '2026-05-19T12:00:00Z',
      insights: [],
    },
    meta: { request_id: 'smoke-patrol' },
  })
  mockStreamPaperQa.mockResolvedValue(undefined)
}

async function mountRoute(path: string) {
  setActivePinia(createPinia())
  const router = createRouter({
    history: createMemoryHistory(),
    routes,
  })
  await router.push(path)
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

describe('smoke routes integration (答辩路径)', () => {
  beforeEach(() => {
    mockListPapers.mockReset()
    mockGetPaper.mockReset()
    mockGetPaperGraph.mockReset()
    mockGetPaperStatus.mockReset()
    mockUploadPaper.mockReset()
    mockRunPatrol.mockReset()
    mockStreamPaperQa.mockReset()
    seedHappyApiMocks()
  })

  it('mounts Home at /', async () => {
    const { wrapper, router } = await mountRoute('/')

    expect(router.currentRoute.value.name).toBe(RouteName.Home)
    expect(wrapper.find('.home-title').exists()).toBe(true)
    expect(wrapper.text()).toContain(HOME_BASELINE_COPY.primaryCta)
  })

  it('mounts Papers at /papers and loads list', async () => {
    const { wrapper, router } = await mountRoute('/papers')

    expect(router.currentRoute.value.name).toBe(RouteName.Papers)
    expect(wrapper.find('.papers-title').text()).toBe(PAPERS_BASELINE_COPY.title)
    expect(mockListPapers).toHaveBeenCalled()
  })

  it('mounts Paper Detail at /papers/:paperId', async () => {
    const { wrapper, router } = await mountRoute('/papers/hss-001')

    expect(router.currentRoute.value.name).toBe(RouteName.PaperDetail)
    expect(mockGetPaper).toHaveBeenCalledWith('hss-001')
    expect(wrapper.find('.detail-header__title').text()).toBe('Smoke 论文')
  })

  it('mounts Graph at /papers/:paperId/graph', async () => {
    const { wrapper, router } = await mountRoute('/papers/hss-001/graph')

    expect(router.currentRoute.value.name).toBe(RouteName.PaperGraph)
    expect(mockGetPaperGraph).toHaveBeenCalledWith('hss-001')
    expect(wrapper.find('.paper-graph-smoke-stub').exists()).toBe(true)
  })

  it('mounts Patrol at /patrol', async () => {
    const { wrapper, router } = await mountRoute('/patrol')

    expect(router.currentRoute.value.name).toBe(RouteName.Patrol)
    expect(wrapper.find('.patrol-view__title').text()).toBe(PATROL_BASELINE_COPY.pageTitle)
    expect(mockListPapers).toHaveBeenCalled()
  })
})

describe('smoke routes robustness (API failures)', () => {
  beforeEach(() => {
    mockListPapers.mockReset()
    mockGetPaper.mockReset()
    mockGetPaperGraph.mockReset()
    mockGetPaperStatus.mockReset()
    mockUploadPaper.mockReset()
    mockRunPatrol.mockReset()
    mockStreamPaperQa.mockReset()
    seedHappyApiMocks()
  })

  it('Papers survives listPapers rejection on mount', async () => {
    mockListPapers.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))

    const { wrapper } = await mountRoute('/papers')

    expect(wrapper.find('.papers-title').exists()).toBe(true)
    expect(wrapper.find('.papers').exists()).toBe(true)
  })

  it('Detail survives getPaper rejection without crashing', async () => {
    mockGetPaper.mockRejectedValue(new ApiClientError({ code: 'NOT_FOUND', message: '论文不存在' }, 404))

    const { wrapper } = await mountRoute('/papers/missing')

    expect(wrapper.find('.paper-detail').exists()).toBe(true)
    expect(wrapper.find('.detail-header').exists()).toBe(false)
  })

  it('Graph shows error panel when getPaperGraph rejects', async () => {
    mockGetPaperGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const { wrapper } = await mountRoute('/papers/hss-001/graph')

    expect(wrapper.find('.graph-view__error-panel').exists()).toBe(true)
    expect(wrapper.find('.graph-view__error-panel .el-alert-stub').attributes('data-title')).toBe('图谱未就绪')
    expect(wrapper.find('.paper-graph-smoke-stub').exists()).toBe(false)
  })

  it('Graph shows generic error when getPaperGraph rejects with network Error', async () => {
    mockGetPaperGraph.mockRejectedValue(new Error('network timeout'))

    const { wrapper } = await mountRoute('/papers/hss-001/graph')

    expect(wrapper.find('.graph-view__error-panel').exists()).toBe(true)
    expect(wrapper.find('.graph-view__error-panel .el-alert-stub').attributes('data-title')).toBe('network timeout')
  })
})
