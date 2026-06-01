/**
 * V1 DoD B-06 / B-07 — GET graph UnifiedPaperGraph + FE G6 adapter 前后端联调联试。
 *
 * 覆盖：功能可用、边界鲁棒、红灯异常（409 GRAPH_NOT_READY / 404）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import * as papersApi from '@/api/papers'
import * as client from '@/api/client'
import type { PaperDetail, UnifiedPaperGraph } from '@/api/types'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { buildG6GraphData, buildHighlightStateMap, toG6GraphPayload } from '@/utils/paperGraph'
import { readFrontendSource } from '@/test/helpers/designTokens'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'

const unifiedGraph = graphFixture.data as UnifiedPaperGraph

const mockFetchDetail = vi.fn()
const mockFetchGraph = vi.fn()

const paperStoreState: {
  loading: boolean
  currentPaper: PaperDetail
  currentGraph: UnifiedPaperGraph | null
  fetchDetail: typeof mockFetchDetail
  fetchGraph: typeof mockFetchGraph
} = {
  loading: false,
  currentPaper: {
    paper_id: 'hss-001',
    title: '测试论文',
    status: 'ready',
    paradigm: 'HSS',
    created_at: '2026-05-19T10:00:00Z',
  },
  currentGraph: null,
  fetchDetail: mockFetchDetail,
  fetchGraph: mockFetchGraph,
}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ query: {} }),
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: vi.fn(),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

import PaperDetailView from '@/views/PaperDetailView.vue'
import PaperGraphView from '@/views/PaperGraphView.vue'

const detailStubs = {
  PaperGraph: {
    props: ['graph', 'highlightNodeId', 'compact'],
    template:
      '<div class="paper-graph-stub" :data-nodes="graph?.nodes?.length ?? 0" :data-highlight="highlightNodeId" />',
  },
  PaperMetadataCard: { template: '<div class="paper-metadata-stub" />' },
  PaperStatusPanel: { template: '<div class="paper-status-panel-stub" />' },
  BadgeParadigm: true,
  BadgeStatus: true,
  'el-input': {
    props: ['modelValue', 'disabled'],
    template:
      '<textarea class="qa-textarea" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    template: '<button type="button" :disabled="disabled" @click="$attrs.onClick?.()"><slot /></button>',
    props: ['disabled'],
  },
  'el-space': { template: '<div><slot /></div>' },
  TagCitation: true,
  'el-alert': {
    props: ['title'],
    template: '<div class="detail-qa__alert" :data-title="title" />',
  },
}

const graphViewStubs = {
  PaperGraph: {
    props: ['graph', 'highlightNodeId', 'fullBleed'],
    template: '<div class="paper-graph-stub" :data-highlight="highlightNodeId" />',
  },
  GraphToolbar: {
    props: ['disabled'],
    template: '<div class="graph-toolbar-stub" :data-disabled="disabled ? \'true\' : \'false\'" />',
  },
  GraphLegend: { template: '<div class="graph-legend-stub" />' },
  GraphNodeDrawer: { template: '<div class="graph-node-drawer-stub" />' },
  BadgeParadigm: true,
  'el-alert': {
    props: ['title', 'description'],
    template: '<div class="graph-alert-stub" :data-title="title" :data-description="description" />',
  },
  'el-button': {
    template: '<button type="button" @click="$attrs.onClick?.()"><slot /></button>',
  },
  RouterLink: { template: '<a><slot /></a>' },
}

describe('V1 DoD B-06 — GET /papers/{id}/graph UnifiedPaperGraph (static + client)', () => {
  it('getPaperGraph client targets frozen path and UnifiedPaperGraph type', () => {
    const papersSrc = readFrontendSource('api/papers.ts')
    expect(papersSrc).toContain('getPaperGraph')
    expect(papersSrc).toContain('UnifiedPaperGraph')
    expect(papersSrc).toContain('/papers/${paperId}/graph')
  })

  it('graph-hss fixture matches UnifiedPaperGraph flat node shape (not G6 nested)', () => {
    expect(unifiedGraph.paper_id).toBe('hss-001')
    const node = unifiedGraph.nodes[0]
    expect(node?.label).toBeTruthy()
    expect(node?.type).toBeTruthy()
    expect(node?.id).toBeTruthy()
    expect(node?.data).toEqual({})
  })

  it('getPaperGraph parses graph-hss fixture envelope', async () => {
    const getDataSpy = vi.spyOn(client, 'getData').mockResolvedValue(graphFixture)

    const result = await papersApi.getPaperGraph('hss-001')

    expect(getDataSpy).toHaveBeenCalledWith('/papers/hss-001/graph')
    expect(result.data.paper_id).toBe('hss-001')
    expect(result.data.nodes.length).toBeGreaterThan(0)
    expect(result.data.nodes[0]?.label).toBe('核心论点')
    getDataSpy.mockRestore()
  })

  it('M2 QA citation targets (n1/n2/n_lens) exist in graph-hss fixture', () => {
    const ids = unifiedGraph.nodes.map((node) => node.id)
    expect(ids).toContain('n1')
    expect(ids).toContain('n2')
    expect(ids).toContain('n_lens')
  })
})

describe('V1 DoD B-06 / B-07 — FE↔BE functional graph path', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchDetail.mockResolvedValue(undefined)
    mockFetchGraph.mockImplementation(async () => {
      paperStoreState.currentGraph = unifiedGraph
    })
    paperStoreState.currentPaper = {
      paper_id: 'hss-001',
      title: '测试论文',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
    paperStoreState.currentGraph = unifiedGraph
  })

  it('DetailView loads UnifiedPaperGraph preview via fetchGraph', async () => {
    paperStoreState.currentGraph = null

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: detailStubs },
    })
    await flushPromises()

    expect(mockFetchGraph).toHaveBeenCalledWith('hss-001')
    expect(wrapper.find('.paper-graph-stub').attributes('data-nodes')).toBe(String(unifiedGraph.nodes.length))
  })

  it('buildG6GraphData converts API UnifiedPaperGraph for PaperGraph canvas', () => {
    const payload = buildG6GraphData(unifiedGraph)
    expect(payload.nodes.length).toBe(unifiedGraph.nodes.length)
    expect(payload.nodes[0]?.data.label).toBe('核心论点')
    expect(payload.nodes[0]?.data.size).toBeDefined()
  })

  it('highlight map chains citation node n_lens to graph fixture label', () => {
    const nodeIds = unifiedGraph.nodes.map((node) => node.id)
    const states = buildHighlightStateMap(nodeIds, 'n_lens')
    expect(states.n_lens).toBe('active')
    const lens = unifiedGraph.nodes.find((node) => node.id === 'n_lens')
    expect(lens?.label).toBe('历史制度主义')
  })
})

describe('V1 DoD B-06 — boundary guards', () => {
  it('toG6GraphPayload handles empty nodes without throwing', () => {
    const emptyGraph: UnifiedPaperGraph = {
      paper_id: 'empty-001',
      paradigm: 'HSS',
      nodes: [],
      edges: [],
    }
    const payload = toG6GraphPayload(emptyGraph)
    expect(payload.nodes).toEqual([])
    expect(payload.edges).toEqual([])
  })

  it('buildG6GraphData tolerates unknown ?node= highlight id', () => {
    const nodeIds = unifiedGraph.nodes.map((node) => node.id)
    const states = buildHighlightStateMap(nodeIds, 'missing-node')
    expect(states['missing-node']).toBeUndefined()
    expect(states.n1).toEqual([])
  })
})

describe('V1 DoD B-06 — red path error feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchDetail.mockResolvedValue(undefined)
    paperStoreState.currentPaper = {
      paper_id: 'hss-002',
      title: '处理中',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
    paperStoreState.currentGraph = null
  })

  it('getPaperGraph 409 GRAPH_NOT_READY propagates ApiClientError', async () => {
    vi.spyOn(client, 'getData').mockRejectedValue(
      new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱尚未就绪，请轮询 status 接口' }, 409),
    )

    await expect(papersApi.getPaperGraph('hss-002')).rejects.toMatchObject({
      code: 'GRAPH_NOT_READY',
      statusCode: 409,
    })
  })

  it('PaperGraphView shows baseline copy on GRAPH_NOT_READY', async () => {
    mockFetchDetail.mockResolvedValue(undefined)
    mockFetchGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱尚未就绪' }, 409))

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-002' },
      global: { stubs: graphViewStubs },
    })
    await flushPromises()

    const alert = wrapper.find('.graph-view__error-panel .graph-alert-stub')
    expect(alert.attributes('data-title')).toBe(GRAPH_BASELINE_COPY.graphNotReadyTitle)
    expect(alert.attributes('data-description')).toBe(GRAPH_BASELINE_COPY.graphNotReadyDescription)
    expect(wrapper.find('.graph-toolbar-stub').attributes('data-disabled')).toBe('true')
    expect(wrapper.find('.paper-graph-stub').exists()).toBe(false)
  })
})

describe('V1 DoD B-07 — toG6GraphPayload vs BE GraphStore.to_g6()', () => {
  it('toG6GraphPayload converts UnifiedPaperGraph on FE only', () => {
    const payload = toG6GraphPayload(unifiedGraph)
    expect(payload.nodes[0]?.id).toBe('n1')
    expect(payload.nodes[0]?.data.label).toBe('核心论点')
    expect(payload.nodes[0]?.data.nodeType).toBe('Thesis')
    expect(unifiedGraph.nodes[0]?.label).toBe('核心论点')
    expect(unifiedGraph.nodes[0]?.type).toBe('Thesis')
  })

  it('papers API module does not perform G6 conversion (B-07 boundary)', () => {
    const papersSrc = readFrontendSource('api/papers.ts')
    expect(papersSrc).not.toContain('toG6GraphPayload')
    expect(papersSrc).not.toContain('buildG6GraphData')
  })

  it('PaperGraph converts UnifiedPaperGraph via buildG6GraphData in paperGraph utils', () => {
    const graphSrc = readFrontendSource('components/graph/PaperGraph.vue')
    expect(graphSrc).toContain('buildG6GraphData')
    expect(graphSrc).toContain('UnifiedPaperGraph')
    const utilsSrc = readFrontendSource('utils/paperGraph.ts')
    expect(utilsSrc).toContain('toG6GraphPayload')
    expect(utilsSrc).not.toContain('to_g6')
  })
})
