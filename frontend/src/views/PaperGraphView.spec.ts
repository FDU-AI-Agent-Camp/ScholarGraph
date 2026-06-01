import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { ApiClientError } from '@/api/client'
import type { PaperDetail, UnifiedPaperGraph } from '@/api/types'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { RouteName } from '@/router/meta'

const mockFetchGraph = vi.fn()
const mockFetchDetail = vi.fn()
const mockReplace = vi.fn()
const mockPush = vi.fn()
const routeQuery = { node: 'n1' as string | undefined }

const paperStoreState = reactive({
  currentGraph: null as UnifiedPaperGraph | null,
  currentPaper: null as PaperDetail | null,
  fetchGraph: mockFetchGraph,
  fetchDetail: mockFetchDetail,
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useRoute: () => ({ query: routeQuery }),
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-stub" :href="String(to)"><slot /></a>',
  },
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

import PaperGraphView from '@/views/PaperGraphView.vue'

const sampleGraph: UnifiedPaperGraph = {
  paper_id: 'hss-001',
  paradigm: 'HSS',
  nodes: [
    { id: 'n1', label: '核心论点', type: 'Thesis', data: {} },
    { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
  ],
  edges: [{ id: 'e1', source: 'n2', target: 'n1', label: 'SUB_ARGUMENT_OF', type: 'SUB_ARGUMENT_OF' }],
}

const paperGraphStub = {
  props: ['graph', 'highlightNodeId', 'fullBleed'],
  emits: ['nodeClick'],
  template:
    '<div class="paper-graph-stub" :data-highlight="highlightNodeId" :data-full-bleed="fullBleed ? \'true\' : \'false\'"><button class="emit-node" @click="$emit(\'nodeClick\', \'n2\')">node</button></div>',
}

const graphOverlayStubs = {
  GraphLegend: { template: '<div class="graph-legend-stub" />' },
  GraphNodeDrawer: {
    props: ['modelValue', 'node'],
    template:
      '<div class="graph-node-drawer-stub" :data-open="modelValue ? \'true\' : \'false\'" :data-node-id="node?.id ?? \'\'" />',
  },
}

describe('PaperGraphView', () => {
  beforeEach(() => {
    mockFetchGraph.mockReset()
    mockFetchDetail.mockReset()
    mockReplace.mockReset()
    mockPush.mockReset()
    routeQuery.node = 'n1'
    paperStoreState.currentGraph = null
    paperStoreState.currentPaper = {
      paper_id: 'hss-001',
      title: '测试论文',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
  })

  it('shows GRAPH_NOT_READY guidance when graph fetch fails with 409', async () => {
    mockFetchGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-002' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: true,
          BadgeParadigm: true,
          ...graphOverlayStubs,
          'el-alert': {
            props: ['title', 'description'],
            template: '<div class="graph-alert" :data-title="title" :data-desc="description" />',
          },
          'el-button': {
            template: '<button type="button" @click="$attrs.onClick?.()"><slot /></button>',
          },
        },
      },
    })

    await flushPromises()

    const alert = wrapper.find('.graph-view__error-panel .graph-alert')
    expect(alert.attributes('data-title')).toBe(GRAPH_BASELINE_COPY.graphNotReadyTitle)
    expect(alert.attributes('data-desc')).toContain('ready')
    expect(wrapper.find('.graph-view__error-cta').exists()).toBe(true)
  })

  it('renders canvas-first full-bleed stage and passes route highlight to PaperGraph', async () => {
    mockFetchGraph.mockImplementation(async () => {
      paperStoreState.currentGraph = sampleGraph
      return sampleGraph
    })

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-001' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: { template: '<div class="graph-toolbar-stub" />' },
          BadgeParadigm: true,
          ...graphOverlayStubs,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.graph-view').exists()).toBe(true)
    expect(wrapper.find('.graph-view__stage').exists()).toBe(true)
    expect(wrapper.find('.graph-view__title').text()).toBe(GRAPH_BASELINE_COPY.pageTitle)
    expect(wrapper.find('.graph-view__paper-id').text()).toBe('hss-001')
    expect(wrapper.find('.graph-toolbar-stub').exists()).toBe(true)
    expect(mockFetchGraph).toHaveBeenCalledWith('hss-001')
    expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
    expect(wrapper.find('.paper-graph-stub').attributes('data-full-bleed')).toBe('true')
    expect(wrapper.find('.graph-view__back').attributes('href')).toContain('/papers/hss-001')
    expect(wrapper.find('.graph-view__counts').text()).toContain('节点 2')
    expect(wrapper.find('.graph-view__counts').text()).toContain('边 1')
    expect(wrapper.find('.graph-legend-stub').exists()).toBe(true)
    expect(wrapper.find('.graph-node-drawer-stub').attributes('data-open')).toBe('true')
    expect(wrapper.find('.graph-node-drawer-stub').attributes('data-node-id')).toBe('n1')
    expect(wrapper.find('.graph-view__mobile-banner').exists()).toBe(true)
  })

  it('opens node drawer when a graph node is clicked', async () => {
    routeQuery.node = undefined
    mockFetchGraph.mockImplementation(async () => {
      paperStoreState.currentGraph = sampleGraph
      return sampleGraph
    })

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-001' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: true,
          BadgeParadigm: true,
          ...graphOverlayStubs,
        },
      },
    })

    await flushPromises()
    await wrapper.find('.emit-node').trigger('click')
    await flushPromises()

    expect(wrapper.find('.graph-node-drawer-stub').attributes('data-open')).toBe('true')
    expect(wrapper.find('.graph-node-drawer-stub').attributes('data-node-id')).toBe('n2')
  })

  it('disables toolbar while graph fetch fails', async () => {
    mockFetchGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-002' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: {
            props: ['disabled'],
            template: '<div class="graph-toolbar-stub" :data-disabled="disabled ? \'true\' : \'false\'" />',
          },
          BadgeParadigm: true,
          ...graphOverlayStubs,
          'el-alert': true,
          'el-button': true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.graph-toolbar-stub').attributes('data-disabled')).toBe('true')
    expect(wrapper.find('.paper-graph-stub').exists()).toBe(false)
  })

  it('navigates back to detail when error CTA is clicked', async () => {
    mockFetchGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-002' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: true,
          BadgeParadigm: true,
          ...graphOverlayStubs,
          'el-alert': true,
          'el-button': {
            inheritAttrs: false,
            template:
              '<button type="button" class="graph-view__error-cta" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
          },
        },
      },
    })

    await flushPromises()
    await wrapper.find('.graph-view__error-cta').trigger('click')

    expect(mockPush).toHaveBeenCalledWith('/papers/hss-002')
  })

  it('shows generic error without CTA when fetch fails with non-409 code', async () => {
    mockFetchGraph.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-002' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: true,
          BadgeParadigm: true,
          ...graphOverlayStubs,
          'el-alert': {
            props: ['title'],
            template: '<div class="graph-alert" :data-title="title" />',
          },
          'el-button': true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.graph-view__error-panel .graph-alert').attributes('data-title')).toBe('服务不可用')
    expect(wrapper.find('.graph-view__error-cta').exists()).toBe(false)
  })

  it('syncs highlight query when a graph node is clicked', async () => {
    mockFetchGraph.mockImplementation(async () => {
      paperStoreState.currentGraph = sampleGraph
      return sampleGraph
    })

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-001' },
      global: {
        stubs: {
          PaperGraph: paperGraphStub,
          GraphToolbar: true,
          BadgeParadigm: true,
          ...graphOverlayStubs,
        },
      },
    })

    await flushPromises()
    await wrapper.find('.emit-node').trigger('click')

    expect(mockReplace).toHaveBeenCalledWith({
      name: RouteName.PaperGraph,
      params: { paperId: 'hss-001' },
      query: { node: 'n2' },
    })
  })
})
