import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperDetail, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { ApiClientError } from '@/api/client'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { EXTRACT_HEURISTIC_FALLBACK_MESSAGE } from '@/utils/extractWarnings'
import { RouteName } from '@/router/meta'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import { answerPanelTypographyMatchesBaseline, citationTagMixedLayout } from '@/test/helpers/copyDiscipline'
import { extractStyleBlocks, usesSynchronousHighlightHandlers } from '@/test/helpers/motionDiscipline'

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
    nodes: [
      { id: 'n1', label: '核心论点', type: 'Thesis', data: {} },
      { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
    ],
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
    emits: ['nodeClick'],
    template:
      '<div class="paper-graph-stub" :data-highlight="highlightNodeId"><button type="button" class="graph-node-trigger" @click="$emit(\'nodeClick\', \'n2\')">node</button></div>',
  },
  PaperMetadataCard: {
    props: ['classification'],
    template: '<div class="paper-metadata-stub" />',
  },
  PaperStatusPanel: { template: '<div class="paper-status-panel-stub" />' },
  BadgeParadigm: true,
  BadgeStatus: true,
  'el-divider': true,
  'el-input': {
    props: ['modelValue', 'disabled', 'placeholder'],
    template:
      '<textarea class="qa-textarea" :disabled="disabled" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    props: ['disabled'],
    template: '<button type="button" :disabled="disabled" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-space': { template: '<div class="el-space-stub"><slot /></div>' },
  TagCitation: {
    props: ['label', 'nodeId', 'active'],
    template:
      '<button class="citation-tag tag-citation" :class="{ \'tag-citation--active\': active }" @click="$emit(\'click\')">{{ label }} ({{ nodeId }})</button>',
  },
  'el-alert': {
    props: ['title', 'type'],
    template: '<div class="el-alert-stub" :data-type="type" :data-title="title" />',
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

    it('keeps left-column module order: metadata → status → QA', async () => {
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      const mainHtml = wrapper.find('.detail-main').html()
      const metadataIndex = mainHtml.indexOf('paper-metadata-stub')
      const statusIndex = mainHtml.indexOf('paper-status-panel-stub')
      const qaIndex = mainHtml.indexOf('detail-qa')

      expect(metadataIndex).toBeGreaterThanOrEqual(0)
      expect(statusIndex).toBeGreaterThan(metadataIndex)
      expect(qaIndex).toBeGreaterThan(statusIndex)
      expect(mainHtml.indexOf('detail-graph')).toBe(-1)
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

  describe('F.2.3 extract fallback warning (X15/X18/X19)', () => {
    it('shows graph-area warning alert when paper detail has extract_heuristic_fallback', async () => {
      paperStoreState.currentPaper = {
        ...paperStoreState.currentPaper,
        extract_warnings: ['extract_heuristic_fallback'],
      }

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      const warning = wrapper.findAll('.el-alert-stub').find((node) => node.attributes('data-type') === 'warning')
      expect(warning?.attributes('data-title')).toBe(EXTRACT_HEURISTIC_FALLBACK_MESSAGE)
      expect(wrapper.find('.detail-graph__extract-warning').exists()).toBe(true)
    })

    it('does not show extract fallback alert when extract_warnings empty', async () => {
      paperStoreState.currentPaper = {
        ...paperStoreState.currentPaper,
        extract_warnings: [],
      }

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      const warning = wrapper.findAll('.el-alert-stub').find((node) => node.attributes('data-type') === 'warning')
      expect(warning).toBeUndefined()
    })
  })

  describe('§1.4.4 QA baseline copy and answer panel (5.6)', () => {
    it('uses baseline placeholder on question textarea', async () => {
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })

      await flushPromises()

      expect((wrapper.find('.qa-textarea').element as HTMLTextAreaElement).placeholder).toBe(
        DETAIL_BASELINE_COPY.qaPlaceholder,
      )
      expect(wrapper.find('.detail-qa__answer-panel').exists()).toBe(false)
    })

    it('styles answer panel with subtle background and body-lg typography', async () => {
      mockStreamPaperQa.mockImplementation(
        async (
          _paperId: string,
          _question: string,
          handlers: {
            onDone?: (data: { answer_id: string; answer?: string }) => void
          },
        ) => {
          handlers.onDone?.({ answer_id: 'ans-1', answer: '答案' })
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

      const panel = wrapper.find('.detail-qa__answer-panel')
      expect(panel.classes()).toContain('text-body-lg')
      expect(panel.attributes('style') ?? '').not.toContain('background')
    })

    it('uses §1.4.1 subtle surface token (#FAFBFC) on answer panel', () => {
      const tokens = loadDesignTokenMap()
      const detailSrc = readFrontendSource('views/PaperDetailView.vue')

      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(detailSrc).toContain('.detail-qa__answer-panel')
      expect(detailSrc).toContain('background: var(--color-bg-subtle)')
    })
  })

  describe('§1.4.4 typography checklist', () => {
    it('answer panel mounts with Body-lg + readable answer text (pre-wrap via CSS)', async () => {
      const detailSrc = readFrontendSource('views/PaperDetailView.vue')
      expect(answerPanelTypographyMatchesBaseline(detailSrc, extractStyleBlocks(detailSrc))).toBe(true)

      mockStreamPaperQa.mockImplementation(
        async (
          _paperId: string,
          _question: string,
          handlers: { onDone?: (data: { answer_id: string; answer?: string }) => void },
        ) => {
          handlers.onDone?.({
            answer_id: 'ans-1',
            answer: '第一行\n第二行',
          })
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

      const panel = wrapper.find('.detail-qa__answer-panel')
      expect(panel.classes()).toContain('text-body-lg')
      expect(wrapper.find('.detail-qa__answer-text').text()).toContain('第一行')
      expect(wrapper.find('.detail-qa__answer-text').classes()).not.toContain('text-mono')
    })

    it('citation tags expose label + (node_id) mono mix for SSE path', async () => {
      expect(citationTagMixedLayout(readFrontendSource('components/ui/TagCitation.vue'))).toBe(true)
    })
  })

  describe('§1.4.3 citation ↔ graph highlight (5.8)', () => {
    async function mountWithTwoCitations() {
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
          handlers.onCitation?.({ paper_id: 'hss-001', node_id: 'n2', label: '分论点' })
          handlers.onDone?.({ answer_id: 'ans-1' })
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

      return wrapper
    }

    it('activates TagCitation and graph highlight together on SSE citation', async () => {
      const wrapper = await mountWithTwoCitations()

      expect(wrapper.findAll('.citation-tag')).toHaveLength(2)
      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n2')
      expect(wrapper.findAll('.tag-citation--active')).toHaveLength(1)
    })

    it('updates graph highlight when another citation tag is clicked', async () => {
      const wrapper = await mountWithTwoCitations()
      const tags = wrapper.findAll('.citation-tag')

      await tags[0]?.trigger('click')

      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
      expect(tags[0]?.classes()).toContain('tag-citation--active')
      expect(tags[1]?.classes()).not.toContain('tag-citation--active')
    })

    it('syncs Tag and graph highlight in the same tick on citation click (§1.4.3 checklist)', async () => {
      const detailSrc = readFrontendSource('views/PaperDetailView.vue')
      const script = detailSrc.match(/<script[^>]*>([\s\S]*?)<\/script>/)?.[1] ?? ''
      expect(usesSynchronousHighlightHandlers(script)).toBe(true)

      const wrapper = await mountWithTwoCitations()
      const tags = wrapper.findAll('.citation-tag')
      await tags[0]?.trigger('click')

      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
      expect(tags[0]?.classes()).toContain('tag-citation--active')
    })

    it('updates active citation when compact graph emits node-click', async () => {
      const wrapper = await mountWithTwoCitations()

      await wrapper.find('.graph-node-trigger').trigger('click')
      await flushPromises()

      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n2')
      const tags = wrapper.findAll('.citation-tag')
      expect(tags[1]?.classes()).toContain('tag-citation--active')
      expect(tags[0]?.classes()).not.toContain('tag-citation--active')
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
    it('shows streaming cursor and answer panel with body-lg styling hooks', async () => {
      mockStreamPaperQa.mockImplementation(
        async (
          _paperId: string,
          _question: string,
          handlers: {
            onMessage?: (data: { delta: string }) => void
          },
        ) => {
          handlers.onMessage?.({ delta: '流式' })
          await new Promise(() => {})
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

      expect(wrapper.find('.detail-qa__answer-panel').exists()).toBe(true)
      expect(wrapper.find('.detail-qa__cursor').exists()).toBe(true)
      expect(wrapper.find('.detail-qa__answer-text').text()).toBe('流式')
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
      await wrapper.find('.qa-textarea').setValue('问题？')
      const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
      await askButton?.trigger('click')
      await flushPromises()

      expect(mockStreamPaperQa).toHaveBeenCalledWith('hss-001', '问题？', expect.any(Object), expect.any(AbortSignal))
      expect(wrapper.find('.detail-qa__answer-text').text()).toBe('完整答案')
      expect(wrapper.find('.detail-qa__citations-label').text()).toContain(DETAIL_BASELINE_COPY.citationLabel)
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

      expect(wrapper.find('.detail-qa__answer-text').text()).toBe('错误: 图谱未就绪')
    })
  })

  describe('robustness (API failures)', () => {
    it('renders empty shell when fetchDetail rejects without crashing', async () => {
      paperStoreState.currentPaper = null as unknown as PaperDetail
      mockFetchDetail.mockRejectedValue(new ApiClientError({ code: 'NOT_FOUND', message: '论文不存在' }, 404))

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'missing' },
        global: { stubs: globalStubs },
      })
      await flushPromises()

      expect(wrapper.find('.paper-detail').exists()).toBe(true)
      expect(wrapper.find('.detail-header').exists()).toBe(false)
      expect(wrapper.attributes('data-loading')).not.toBe('true')
    })

    it('clears graphLoading when fetchGraph rejects during preview load', async () => {
      paperStoreState.currentGraph = null as unknown as UnifiedPaperGraph
      mockFetchGraph.mockRejectedValue(new Error('network timeout'))

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: globalStubs },
      })
      await flushPromises()

      expect(wrapper.find('.detail-graph__canvas').attributes('data-loading')).not.toBe('true')
      expect(wrapper.find('.detail-graph__placeholder').exists()).toBe(true)
      expect(wrapper.find('.paper-graph-stub').exists()).toBe(false)
    })
  })
})
