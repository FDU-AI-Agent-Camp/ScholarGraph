/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD B-04 / B-05 — SSE QA 真流契约 + citation payload 前后端联调联试。
 *
 * 覆盖：功能可用、边界鲁棒、红灯异常（HTTP 404 / SSE error+done / 连接中断）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { parseQaStreamEvent } from '@/api/qaStream'
import type { PaperDetail, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { appendUniqueCitation, buildHighlightStateMap } from '@/utils/paperGraph'
import { citationNodeId } from '@/utils/qaCitations'
import { readFrontendSource } from '@/test/helpers/designTokens'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'

const MOCK_DISCLAIMER = '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）'
const graph = graphFixture.data as UnifiedPaperGraph

/** Mirrors backend mock LLM SSE sequence (tests/integration/test_dod_b04_b05.py). */
function buildBackendMockSseFrames() {
  const thesis = graph.nodes.find((node) => node.id === 'n1')
  return [
    { event: 'message', data: { delta: '根据知识图谱上下文，' } },
    {
      event: 'citation',
      data: { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: thesis?.label ?? '核心论点' },
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

function dispatchFramesToHandlers(
  frames: ReadonlyArray<{ event: string; data: Record<string, unknown> }>,
  handlers: {
    onMessage?: (data: { delta: string }) => void
    onCitation?: (data: QaStreamCitationData) => void
    onDone?: (data: { answer_id: string; answer?: string }) => void
    onError?: (message: string) => void
  },
): void {
  for (const frame of frames) {
    const parsed = parseQaStreamEvent(frame.event, JSON.stringify(frame.data))
    if (!parsed) continue
    if (parsed.type === 'message') handlers.onMessage?.(parsed.data)
    if (parsed.type === 'citation') handlers.onCitation?.(parsed.data)
    if (parsed.type === 'done') handlers.onDone?.(parsed.data)
    if (parsed.type === 'error') handlers.onError?.(parsed.data.message)
  }
}

describe('V1 DoD B-04 — POST qa/stream SSE contract (static)', () => {
  it('qaStream client uses frozen POST path and fetch-event-source', () => {
    const qaSrc = readFrontendSource('api/qaStream.ts')
    expect(qaSrc).toContain('/papers/${paperId}/qa/stream')
    expect(qaSrc).toContain('fetchEventSource')
    expect(qaSrc).toContain("method: 'POST'")
    expect(qaSrc).toContain("'text/event-stream'")
  })

  it('parses api-contract §8 message / citation / done frames', () => {
    const frames = buildBackendMockSseFrames()
    const parsed = frames.map((frame) => parseQaStreamEvent(frame.event, JSON.stringify(frame.data)))
    expect(parsed.every((item) => item !== null)).toBe(true)
    expect(parsed[1]?.type).toBe('citation')
    if (parsed[1]?.type === 'citation') {
      expect(parsed[1].data.paper_id).toBe('hss-001')
      expect(citationNodeId(parsed[1].data)).toBe('n1')
    }
  })

  it('maps citation node_id to graph-hss fixture (B-05 verifiable)', () => {
    const cite = buildBackendMockSseFrames()[1].data
    expect(cite.type).toBe('node')
    if (cite.type !== 'node') {
      return
    }
    const node = graph.nodes.find((item) => item.id === cite.node_id)
    expect(node).toBeDefined()
    expect(node?.label).toBe(cite.label)
  })
})

describe('V1 DoD B-04 / B-05 — FE↔BE functional QA stream', () => {
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

  it('DetailView renders mock SSE answer, citation tag, and graph highlight', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_paperId: string, _question: string, handlers: Parameters<typeof dispatchFramesToHandlers>[1]) => {
        dispatchFramesToHandlers(buildBackendMockSseFrames(), handlers)
      },
    )

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: detailStubs },
    })
    await flushPromises()
    await wrapper.find('.qa-textarea').setValue('这篇论文的核心论点是什么？')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '提问')
      ?.trigger('click')
    await flushPromises()

    expect(mockStreamPaperQa).toHaveBeenCalledWith(
      'hss-001',
      '这篇论文的核心论点是什么？',
      expect.any(Object),
      expect.any(AbortSignal),
    )
    expect(wrapper.find('.detail-qa__answer-text').text()).toContain('Mock 答复')
    expect(wrapper.find('.citation-tag').text()).toContain('核心论点')
    expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')
  })

  it('chains BE citation frame into highlight map (B-05 parity)', () => {
    const citeFrame = buildBackendMockSseFrames()[1]
    const parsed = parseQaStreamEvent(citeFrame.event, JSON.stringify(citeFrame.data))
    expect(parsed?.type).toBe('citation')
    if (parsed?.type !== 'citation') {
      return
    }
    const nodeIds = graph.nodes.map((node) => node.id)
    const states = buildHighlightStateMap(nodeIds, citationNodeId(parsed.data))
    expect(states.n1).toBe('active')
  })

  it('appendUniqueCitation deduplicates repeated citation events', () => {
    const cite = { type: 'node' as const, paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }
    const once = appendUniqueCitation([], cite)
    const twice = appendUniqueCitation(once, cite)
    expect(twice).toHaveLength(1)
  })
})

describe('V1 DoD B-04 — boundary guards', () => {
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

  it('blocks QA while paper is not ready', async () => {
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
    expect(mockStreamPaperQa).not.toHaveBeenCalled()
  })

  it('ignores malformed SSE JSON and unknown event types without throwing', () => {
    expect(parseQaStreamEvent('message', '{bad json')).toBeNull()
    expect(parseQaStreamEvent('ping', '{}')).toBeNull()
    expect(parseQaStreamEvent('citation', 'null')).toBeNull()
  })

  it('coerces partial citation payload to strings (parser resilience)', () => {
    const parsed = parseQaStreamEvent('citation', JSON.stringify({ paper_id: 'hss-001' }))
    expect(parsed?.type).toBe('citation')
    if (parsed?.type === 'citation' && parsed.data.type === 'node') {
      expect(parsed.data.paper_id).toBe('hss-001')
      expect(parsed.data.node_id).toBe('')
      expect(parsed.data.label).toBe('')
    }
  })
})

describe('V1 DoD B-04 — red path error feedback', () => {
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
  })

  it('surfaces GRAPH_NOT_FOUND SSE error in answer area', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_paperId: string, _question: string, handlers: { onError?: (message: string) => void }) => {
        dispatchFramesToHandlers(
          [{ event: 'error', data: { code: 'GRAPH_NOT_FOUND', message: '论文 hss-001 的图谱尚未建好' } }],
          handlers,
        )
      },
    )

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: detailStubs },
    })
    await flushPromises()
    await wrapper.find('.qa-textarea').setValue('问题？')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '提问')
      ?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.detail-qa__answer-text').text()).toBe('错误: 论文 hss-001 的图谱尚未建好')
  })

  it('surfaces QA_STREAM_ERROR message from backend SSE error event', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_paperId: string, _question: string, handlers: { onError?: (message: string) => void }) => {
        dispatchFramesToHandlers(
          [{ event: 'error', data: { code: 'QA_STREAM_ERROR', message: 'LLM connection refused' } }],
          handlers,
        )
      },
    )

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-001' },
      global: { stubs: detailStubs },
    })
    await flushPromises()
    await wrapper.find('.qa-textarea').setValue('问题？')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '提问')
      ?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.detail-qa__answer-text').text()).toContain('LLM connection refused')
  })

  it('parses error codes GRAPH_NOT_FOUND and QA_STREAM_ERROR for FE routing', () => {
    for (const code of ['GRAPH_NOT_FOUND', 'QA_STREAM_ERROR'] as const) {
      const parsed = parseQaStreamEvent('error', JSON.stringify({ code, message: `${code} 说明` }))
      expect(parsed?.type).toBe('error')
      if (parsed?.type === 'error') {
        expect(parsed.data.code).toBe(code)
        expect(parsed.data.message).toContain(code)
      }
    }
  })
})

describe('V1 DoD B-05 — citation payload fields', () => {
  it('requires paper_id, node_id, label on citation events', () => {
    const parsed = parseQaStreamEvent(
      'citation',
      JSON.stringify({ type: 'node', paper_id: 'hss-001', node_id: 'n_lens', label: '历史制度主义' }),
    )
    expect(parsed?.type).toBe('citation')
    if (parsed?.type !== 'citation') {
      return
    }
    expect(parsed.data.paper_id).toBeTruthy()
    expect(parsed.data.type).toBe('node')
    if (parsed.data.type === 'node') {
      expect(parsed.data.node_id).toBeTruthy()
    }
    expect(parsed.data.label).toBeTruthy()
  })
})
