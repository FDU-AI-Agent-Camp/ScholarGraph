import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperDetail, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
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
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-stub" :href="String(to)"><slot /></a>',
  },
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
  PaperMetadataCard: {
    props: ['classification'],
    template: '<div class="paper-metadata-stub" />',
  },
  PaperStatusPanel: true,
  BadgeParadigm: true,
  BadgeStatus: true,
  'el-divider': true,
  'el-input': {
    props: ['modelValue', 'disabled'],
    template:
      '<textarea class="qa-textarea" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    props: ['disabled'],
    template: '<button type="button" :disabled="disabled" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-space': { template: '<div class="el-space-stub"><slot /></div>' },
  'el-card': { template: '<div class="answer"><slot /></div>' },
  TagCitation: {
    props: ['label', 'nodeId', 'active'],
    template:
      '<button class="citation-tag tag-citation" :class="{ \'tag-citation--active\': active }" @click="$emit(\'click\')">{{ label }} ({{ nodeId }})</button>',
  },
  'el-alert': {
    props: ['title'],
    template: '<div class="detail-qa__alert" :data-title="title" />',
  },
}

describe('PaperDetailView', () => {
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

  describe('§1.4.2 layout and header (5.1–5.2)', () => {
    it('renders dual-column layout hooks and header meta badges', async () => {
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      expect(wrapper.find('.detail-layout').exists()).toBe(true)
      expect(wrapper.find('.detail-main').exists()).toBe(true)
      expect(wrapper.find('.detail-graph').exists()).toBe(true)
      expect(wrapper.find('.detail-header__back').text()).toContain(DETAIL_BASELINE_COPY.backLink)
      expect(wrapper.find('.detail-header__title').text()).toBe('测试论文')
      expect(wrapper.find('.paper-metadata-stub').exists()).toBe(true)
    })

    it('shows paper_id mono meta and QA / graph section titles from baseline copy', async () => {
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      expect(wrapper.find('.detail-header__paper-id').text()).toBe('hss-001')
      expect(wrapper.find('.detail-qa__title').text()).toBe(DETAIL_BASELINE_COPY.qaSectionTitle)
      expect(wrapper.find('.detail-graph__title').text()).toBe(DETAIL_BASELINE_COPY.graphPreviewTitle)
    })

    it('passes classification into metadata card when present on paper detail', async () => {
      paperStoreState.currentPaper = {
        ...paperStoreState.currentPaper,
        classification: {
          paradigm: 'HSS',
          confidence: 0.95,
          reason: '历史制度主义视角。',
        },
      }

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      expect(wrapper.find('.paper-metadata-stub').exists()).toBe(true)
    })
  })

  describe('§1.4.4 not-ready alert (5.5)', () => {
    it('shows baseline info alert and disabled QA controls when paper is not ready', async () => {
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

      expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
      expect(wrapper.find('.qa-textarea').exists()).toBe(true)
      expect((wrapper.find('.qa-textarea').element as HTMLTextAreaElement).disabled).toBe(true)
      expect(mockStreamPaperQa).not.toHaveBeenCalled()
    })

    it('shows graph preview placeholder and hides compact graph while processing', async () => {
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

      expect(wrapper.find('.detail-graph__placeholder').exists()).toBe(true)
      expect(wrapper.find('.paper-graph-stub').exists()).toBe(false)
      const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
      expect((askButton?.element as HTMLButtonElement).disabled).toBe(true)
    })
  })

  describe('QA SSE', () => {
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
      await wrapper.find('.qa-textarea').setValue('问题？')
      const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
      await askButton?.trigger('click')
      await flushPromises()

      expect(mockStreamPaperQa).toHaveBeenCalledWith('hss-001', '问题？', expect.any(Object), expect.any(AbortSignal))
      expect(wrapper.find('.answer').text()).toBe('完整答案')
      expect(wrapper.find('.citation-tag').text()).toContain('核心论点')
      expect(wrapper.find('.tag-citation--active').exists()).toBe(true)
      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
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
      await wrapper.find('.qa-textarea').setValue('问题？')
      const buttons = wrapper.findAll('button')
      await buttons.find((button) => button.text() === '提问')?.trigger('click')
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
      await wrapper.find('.qa-textarea').setValue('问题？')
      await wrapper
        .findAll('button')
        .find((button) => button.text() === '提问')
        ?.trigger('click')
      await flushPromises()

      expect(wrapper.find('.answer').text()).toBe('错误: 图谱未就绪')
    })
  })
})
