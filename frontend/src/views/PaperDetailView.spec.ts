import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperDetail, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { RouteName } from '@/router/meta'

const mockStreamPaperQa = vi.fn()
const mockFetchDetail = vi.fn()
const mockFetchGraph = vi.fn()
const mockPush = vi.fn()

const paperStoreState: {
  loading: boolean
  currentPaper: PaperDetail
  currentGraph: UnifiedPaperGraph
  fetchDetail: typeof mockFetchDetail
  fetchGraph: typeof mockFetchGraph
} = {
  loading: false,
  currentPaper: {
    paper_id: 'hss-001',
    title: '测试论文',
    status: 'ready' as const,
    paradigm: 'HSS' as const,
    created_at: '2026-05-19T10:00:00Z',
  },
  currentGraph: {
    paper_id: 'hss-001',
    paradigm: 'HSS' as const,
    nodes: [{ id: 'n1', label: '核心论点', type: 'Thesis', data: {} }],
    edges: [],
  },
  fetchDetail: mockFetchDetail,
  fetchGraph: mockFetchGraph,
}

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: (...args: unknown[]) => mockStreamPaperQa(...args),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

import PaperDetailView from '@/views/PaperDetailView.vue'

const globalStubs = {
  PaperGraph: {
    props: ['graph', 'highlightNodeId', 'compact'],
    template: '<div class="paper-graph-stub" :data-highlight="highlightNodeId" />',
  },
  'el-page-header': true,
  'el-descriptions': true,
  'el-descriptions-item': true,
  'el-divider': true,
  'el-input': {
    props: ['modelValue'],
    template: '<textarea @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    template: '<button @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-space': { template: '<div><slot /></div>' },
  'el-card': { template: '<div class="answer"><slot /></div>' },
  TagCitation: {
    props: ['label', 'nodeId', 'active'],
    template:
      '<button class="citation-tag tag-citation" :class="{ \'tag-citation--active\': active }" @click="$emit(\'click\')">{{ label }} ({{ nodeId }})</button>',
  },
  'el-alert': {
    props: ['title'],
    template: '<div class="qa-hint" :data-title="title" />',
  },
  PaperStatusPanel: true,
}

describe('PaperDetailView QA SSE', () => {
  beforeEach(() => {
    mockStreamPaperQa.mockReset()
    mockFetchDetail.mockReset()
    mockFetchGraph.mockReset()
    mockPush.mockReset()
    mockFetchDetail.mockResolvedValue(undefined)
    mockFetchGraph.mockResolvedValue(undefined)
    paperStoreState.currentPaper = {
      paper_id: 'hss-001',
      title: '测试论文',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
  })

  it('collects citation events and exposes clickable tags', async () => {
    mockStreamPaperQa.mockImplementation(
      async (
        _paperId: string,
        _question: string,
        handlers: {
          onMessage?: (data: { delta: string }) => void
          onCitation?: (data: QaStreamCitationData) => void
          onDone?: (data: { answer_id: string; answer?: string }) => void
        },
      ) => {
        handlers.onMessage?.({ delta: '片段' })
        handlers.onCitation?.({ paper_id: 'hss-001', node_id: 'n1', label: '核心论点' })
        handlers.onDone?.({ answer_id: 'ans-1', answer: '完整答案' })
      },
    )

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: globalStubs },
    })

    await flushPromises()
    await wrapper.find('textarea').setValue('问题？')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(mockStreamPaperQa).toHaveBeenCalledWith('hss-001', '问题？', expect.any(Object), expect.any(AbortSignal))
    expect(wrapper.find('.answer').text()).toBe('完整答案')
    expect(wrapper.find('.citation-tag').text()).toContain('核心论点')
    expect(wrapper.find('.tag-citation--active').exists()).toBe(true)
    expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
  })

  it('shows hint and hides QA controls when paper is not ready', async () => {
    paperStoreState.currentPaper = {
      paper_id: 'hss-002',
      title: '处理中',
      status: 'processing',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-002' },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    expect(wrapper.find('.qa-hint').attributes('data-title')).toContain('ready')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(mockStreamPaperQa).not.toHaveBeenCalled()
  })

  it('navigates to graph route with node query after citation highlight', async () => {
    mockStreamPaperQa.mockImplementation(
      async (
        _paperId: string,
        _question: string,
        handlers: {
          onCitation?: (data: QaStreamCitationData) => void
          onDone?: (data: { answer_id: string }) => void
        },
      ) => {
        handlers.onCitation?.({ paper_id: 'hss-001', node_id: 'n1', label: '核心论点' })
        handlers.onDone?.({ answer_id: 'ans-1' })
      },
    )

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: globalStubs },
    })

    await flushPromises()
    await wrapper.find('textarea').setValue('问题？')
    const buttons = wrapper.findAll('button')
    await buttons[0]?.trigger('click')
    await flushPromises()

    const fullGraphButton = buttons.find((button) => button.text().includes('全屏图谱'))
    await fullGraphButton?.trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: RouteName.PaperGraph,
      params: { paperId: 'hss-001' },
      query: { node: 'n1' },
    })
  })

  it('surfaces SSE error message in answer area', async () => {
    mockStreamPaperQa.mockImplementation(
      async (
        _paperId: string,
        _question: string,
        handlers: {
          onError?: (message: string) => void
        },
      ) => {
        handlers.onError?.('图谱未就绪')
      },
    )

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: globalStubs },
    })

    await flushPromises()
    await wrapper.find('textarea').setValue('问题？')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.answer').text()).toBe('错误: 图谱未就绪')
  })
})
