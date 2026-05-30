import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { ApiClientError } from '@/api/client'
import type { UnifiedPaperGraph } from '@/api/types'
import { RouteName } from '@/router/meta'

const mockFetchGraph = vi.fn()
const mockReplace = vi.fn()
const mockPush = vi.fn()
const routeQuery = { node: 'n1' as string | undefined }

const paperStoreState = reactive({
  currentGraph: null as UnifiedPaperGraph | null,
  fetchGraph: mockFetchGraph,
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useRoute: () => ({ query: routeQuery }),
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

describe('PaperGraphView', () => {
  beforeEach(() => {
    mockFetchGraph.mockReset()
    mockReplace.mockReset()
    mockPush.mockReset()
    routeQuery.node = 'n1'
    paperStoreState.currentGraph = null
  })

  it('shows GRAPH_NOT_READY guidance when graph fetch fails with 409', async () => {
    mockFetchGraph.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-002' },
      global: {
        stubs: {
          PaperGraph: true,
          'el-page-header': true,
          'el-alert': {
            props: ['title', 'description'],
            template: '<div class="graph-alert" :data-title="title" :data-desc="description" />',
          },
          'el-descriptions': true,
          'el-descriptions-item': true,
        },
      },
    })

    await flushPromises()

    const alert = wrapper.find('.graph-alert')
    expect(alert.attributes('data-title')).toBe('图谱未就绪')
    expect(alert.attributes('data-desc')).toContain('ready')
  })

  it('renders graph meta and passes route highlight to PaperGraph', async () => {
    mockFetchGraph.mockImplementation(async () => {
      paperStoreState.currentGraph = sampleGraph
      return sampleGraph
    })

    const wrapper = mount(PaperGraphView, {
      props: { paperId: 'hss-001' },
      global: {
        stubs: {
          PaperGraph: {
            props: ['graph', 'highlightNodeId'],
            template: '<div class="paper-graph-stub" :data-highlight="highlightNodeId" />',
          },
          'el-page-header': true,
          'el-descriptions': true,
          'el-descriptions-item': {
            template: '<span class="meta-item"><slot /></span>',
          },
        },
      },
    })

    await flushPromises()

    expect(mockFetchGraph).toHaveBeenCalledWith('hss-001')
    expect(paperStoreState.currentGraph?.paradigm).toBe('HSS')
    expect(paperStoreState.currentGraph?.nodes).toHaveLength(2)
    expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
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
          PaperGraph: {
            props: ['graph', 'highlightNodeId'],
            emits: ['nodeClick'],
            template: '<button class="emit-node" @click="$emit(\'nodeClick\', \'n2\')">node</button>',
          },
          'el-page-header': true,
          'el-descriptions': true,
          'el-descriptions-item': true,
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
