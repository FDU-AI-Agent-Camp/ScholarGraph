/**
 * V1 DoD A-09 / A-11 — M2 多尺度问答 + M4 流水线前后端联调联试。
 *
 * 覆盖：功能可用（三类问题 citation 可复核）、边界鲁棒性、红灯异常反馈。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperDetail, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { parseQaStreamEvent } from '@/api/qaStream'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { appendUniqueCitation, buildHighlightStateMap } from '@/utils/paperGraph'
import { isFailedStatus, isTerminalStatus } from '@/utils/paperStatus'
import { failedStatus, readyStatus } from '@/test/fixtures/paperStatus'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import processingStatusFixture from '../../../docs/api/fixtures/paper-status-hss-002.json'

/** Mirrors backend.graph.qa_samples.M2_HSS_QUESTIONS + docs/v1/eval/qa_samples.md */
const M2_HSS_QUESTIONS = [
  {
    scale: 'summary',
    question: '这篇论文做了什么？请给出核心论点总览。',
    expectedNodeId: 'n1',
    expectedType: 'Thesis',
    scaleTag: '摘要尺度',
  },
  {
    scale: 'detail',
    question: '分论点如何支撑核心论点？',
    expectedNodeId: 'n2',
    expectedType: 'SubArgument',
    scaleTag: '细节尺度',
  },
  {
    scale: 'verification',
    question: '核心论点通过哪些材料、经何种理论视角被论证？',
    expectedNodeId: 'n_lens',
    expectedType: 'AnalyticalLens',
    scaleTag: '验证尺度',
  },
] as const

const MOCK_DISCLAIMER = '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）'

const graph = graphFixture.data as UnifiedPaperGraph
const nodeIndex = Object.fromEntries(graph.nodes.map((node) => [node.id, node]))

function buildM2MockSseFrames(sample: (typeof M2_HSS_QUESTIONS)[number]) {
  const node = nodeIndex[sample.expectedNodeId]
  return [
    { event: 'message', data: { delta: `【${sample.scaleTag}】根据知识图谱上下文，` } },
    {
      event: 'citation',
      data: { paper_id: 'hss-001', node_id: sample.expectedNodeId, label: node?.label ?? sample.expectedNodeId },
    },
    { event: 'message', data: { delta: MOCK_DISCLAIMER } },
    { event: 'done', data: { answer_id: 'ans-hss-001' } },
  ] as const
}

const mockStreamPaperQa = vi.fn()
const mockFetchDetail = vi.fn()
const mockFetchGraph = vi.fn()

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
    status: 'ready',
    paradigm: 'HSS',
    created_at: '2026-05-19T10:00:00Z',
  },
  currentGraph: graph,
  fetchDetail: mockFetchDetail,
  fetchGraph: mockFetchGraph,
}

vi.mock('@/api/qaStream', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/qaStream')>()
  return {
    ...actual,
    streamPaperQa: (...args: unknown[]) => mockStreamPaperQa(...args),
  }
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

import PaperDetailView from '@/views/PaperDetailView.vue'

const detailStubs = {
  PaperGraph: {
    props: ['highlightNodeId'],
    template: '<div class="paper-graph-stub" :data-highlight="highlightNodeId" />',
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
  TagCitation: {
    props: ['label', 'nodeId', 'active'],
    template:
      '<button class="citation-tag" :class="{ \'tag-citation--active\': active }">{{ label }} ({{ nodeId }})</button>',
  },
  'el-alert': {
    props: ['title'],
    template: '<div class="detail-qa__alert" :data-title="title" />',
  },
}

describe('V1 DoD A-09 — M2 multi-scale QA FE↔BE', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchDetail.mockResolvedValue(undefined)
    mockFetchGraph.mockResolvedValue(undefined)
    paperStoreState.currentPaper = {
      paper_id: 'hss-001',
      title: '测试论文',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
    paperStoreState.currentGraph = graph
  })

  describe('functional — three scales with verifiable citations', () => {
    it.each(M2_HSS_QUESTIONS)('$scale: parses BE mock SSE and maps citation to graph node', (sample) => {
      const frames = buildM2MockSseFrames(sample)
      const parsed = frames.map((frame) => parseQaStreamEvent(frame.event, JSON.stringify(frame.data)))
      expect(parsed.every((item) => item !== null)).toBe(true)

      const citation = parsed.find((item) => item?.type === 'citation')
      expect(citation?.type).toBe('citation')
      if (citation?.type !== 'citation') {
        return
      }

      expect(citation.data.node_id).toBe(sample.expectedNodeId)
      expect(citation.data.label).toBe(nodeIndex[sample.expectedNodeId]?.label)

      const nodeIds = graph.nodes.map((node) => node.id)
      const states = buildHighlightStateMap(nodeIds, citation.data.node_id)
      expect(states[sample.expectedNodeId]).toBe('active')

      const messages = parsed
        .filter((item) => item?.type === 'message')
        .map((item) => (item?.type === 'message' ? item.data.delta : ''))
        .join('')
      expect(messages).toContain(sample.scaleTag)
      expect(messages).toContain('Mock 答复')
    })

    it.each(M2_HSS_QUESTIONS)('$scale: DetailView renders citation tag matching graph fixture', async (sample) => {
      mockStreamPaperQa.mockImplementation(
        async (
          _paperId: string,
          _question: string,
          handlers: {
            onMessage?: (data: { delta: string }) => void
            onCitation?: (data: QaStreamCitationData) => void
            onDone?: (data: { answer_id: string }) => void
          },
        ) => {
          for (const frame of buildM2MockSseFrames(sample)) {
            const parsed = parseQaStreamEvent(frame.event, JSON.stringify(frame.data))
            if (!parsed) continue
            if (parsed.type === 'message') handlers.onMessage?.(parsed.data)
            if (parsed.type === 'citation') handlers.onCitation?.(parsed.data)
            if (parsed.type === 'done') handlers.onDone?.(parsed.data)
          }
        },
      )

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: detailStubs },
      })
      await flushPromises()
      await wrapper.find('.qa-textarea').setValue(sample.question)
      await wrapper
        .findAll('button')
        .find((button) => button.text() === '提问')
        ?.trigger('click')
      await flushPromises()

      expect(mockStreamPaperQa).toHaveBeenCalledWith(
        'hss-001',
        sample.question,
        expect.any(Object),
        expect.any(AbortSignal),
      )
      expect(wrapper.find('.citation-tag').text()).toContain(nodeIndex[sample.expectedNodeId]?.label ?? '')
      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe(sample.expectedNodeId)
    })
  })

  describe('boundary — parser and UI guards', () => {
    it('appendUniqueCitation deduplicates repeated SSE citation frames', () => {
      const cite = { paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }
      const once = appendUniqueCitation([], cite)
      const twice = appendUniqueCitation(once, cite)
      expect(twice).toHaveLength(1)
    })

    it('ignores malformed SSE JSON and unknown event types without throwing', () => {
      expect(parseQaStreamEvent('message', '{bad json')).toBeNull()
      expect(parseQaStreamEvent('unknown_event', '{}')).toBeNull()
    })

    it('does not call streamPaperQa for whitespace-only question', async () => {
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: detailStubs },
      })
      await flushPromises()
      await wrapper.find('.qa-textarea').setValue('   ')
      await wrapper
        .findAll('button')
        .find((button) => button.text() === '提问')
        ?.trigger('click')
      await flushPromises()

      expect(mockStreamPaperQa).not.toHaveBeenCalled()
    })

    it('blocks QA input while paper is processing (pipeline not ready)', async () => {
      paperStoreState.currentPaper = {
        paper_id: 'hss-002',
        title: '处理中',
        status: 'processing',
        paradigm: 'HSS',
        created_at: '2026-05-19T10:00:00Z',
      }

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-002' },
        global: { stubs: detailStubs },
      })
      await flushPromises()

      expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
      expect((wrapper.find('.qa-textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    })
  })

  describe('red path — SSE error feedback', () => {
    it('surfaces GRAPH_NOT_FOUND SSE error in answer area', async () => {
      mockStreamPaperQa.mockImplementation(
        async (_paperId: string, _question: string, handlers: { onError?: (message: string) => void }) => {
          const parsed = parseQaStreamEvent(
            'error',
            JSON.stringify({ code: 'GRAPH_NOT_FOUND', message: '论文 hss-001 的图谱尚未建好' }),
          )
          if (parsed?.type === 'error') {
            handlers.onError?.(parsed.data.message)
          }
        },
      )

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: detailStubs },
      })
      await flushPromises()
      await wrapper.find('.qa-textarea').setValue(M2_HSS_QUESTIONS[0].question)
      await wrapper
        .findAll('button')
        .find((button) => button.text() === '提问')
        ?.trigger('click')
      await flushPromises()

      expect(wrapper.find('.detail-qa__answer-text').text()).toContain('图谱尚未建好')
    })

    it('surfaces QA_STREAM_ERROR message from backend SSE error event', () => {
      const parsed = parseQaStreamEvent(
        'error',
        JSON.stringify({ code: 'QA_STREAM_ERROR', message: 'LLM connection refused' }),
      )
      expect(parsed?.type).toBe('error')
      if (parsed?.type === 'error') {
        expect(parsed.data.code).toBe('QA_STREAM_ERROR')
        expect(parsed.data.message).toContain('LLM connection refused')
      }
    })
  })
})

describe('V1 DoD A-11 — M4 pipeline FE↔BE status contract', () => {
  it('ready status fixture enables terminal success path for QA/graph', () => {
    expect(readyStatus.status).toBe('ready')
    expect(isTerminalStatus(readyStatus.status)).toBe(true)
    expect(isFailedStatus(readyStatus)).toBe(false)
    expect(readyStatus.percent).toBe(100)
  })

  it('failed pipeline fixture exposes error_code + failed_during for UI alert', () => {
    expect(isFailedStatus(failedStatus)).toBe(true)
    expect(failedStatus.error_code).toBe('LLM_JSON_INVALID')
    expect(failedStatus.failed_during).toBe('classifying')
    expect(failedStatus.message.length).toBeGreaterThan(0)
  })

  it('processing fixture from hss-002 seed aligns with polling UX (non-terminal)', () => {
    const processingFixture = processingStatusFixture.data
    expect(processingFixture.status).toBe('processing')
    expect(isTerminalStatus(processingFixture.status as 'processing')).toBe(false)
    expect(processingFixture.stage).toBe('classifying')
    expect(processingFixture.percent).toBeGreaterThan(0)
  })
})
