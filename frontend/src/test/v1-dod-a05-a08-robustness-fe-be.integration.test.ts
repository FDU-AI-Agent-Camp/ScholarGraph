/**
 * V1 DoD A-05～A-08 — 绿路径 / 边界 / 红灯鲁棒性（FE↔BE 成对联调）.
 *
 * 与 tests/integration/test_dod_a05_a08_robustness_fe_be.py 成对。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { parseQaStreamEvent } from '@/api/qaStream'
import type { PaperDetail, PaperStatusData, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import { resolvePatrolApiError, validatePatrolPaperIds, validatePatrolSelection } from '@/utils/patrolForm'
import { isFailedStatus } from '@/utils/paperStatus'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'

const mockStreamPaperQa = vi.hoisted(() => vi.fn())
const mockListPapers = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())
const mockPush = vi.hoisted(() => vi.fn())

const paperStoreState: {
  loading: boolean
  currentPaper: PaperDetail
  currentGraph: UnifiedPaperGraph | null
  fetchDetail: ReturnType<typeof vi.fn>
  fetchGraph: ReturnType<typeof vi.fn>
} = {
  loading: false,
  currentPaper: {
    paper_id: 'hss-001',
    title: '测试论文',
    status: 'ready',
    paradigm: 'HSS',
    created_at: '2026-05-19T10:00:00Z',
  },
  currentGraph: {
    paper_id: 'hss-001',
    paradigm: 'HSS',
    nodes: [
      { id: 'n1', label: '核心论点', type: 'Thesis', data: {} },
      { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
    ],
    edges: [],
  },
  fetchDetail: vi.fn(),
  fetchGraph: vi.fn(),
}

vi.mock('@/api/qaStream', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/qaStream')>()
  return {
    ...actual,
    streamPaperQa: (...args: unknown[]) => mockStreamPaperQa(...args),
  }
})

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
}))

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ push: mockPush }),
  }
})

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

import PaperDetailView from '@/views/PaperDetailView.vue'

const detailStubs = {
  PaperGraph: {
    props: ['graph', 'highlightNodeId', 'compact'],
    template: '<div class="paper-graph-stub" :data-highlight="highlightNodeId" />',
  },
  PaperMetadataCard: { template: '<div class="paper-metadata-stub" />' },
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
    props: ['disabled', 'loading'],
    template: '<button type="button" :disabled="disabled" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-space': { template: '<div><slot /></div>' },
  TagCitation: {
    props: ['label', 'nodeId', 'active'],
    template:
      '<button class="citation-tag tag-citation" :class="{ \'tag-citation--active\': active }" @click="$emit(\'click\')">{{ label }}</button>',
  },
  'el-alert': {
    props: ['title'],
    template: '<div class="detail-alert-stub" :data-title="title" />',
  },
  RouterLink: true,
}

describe('V1 DoD A-05～A-08 robustness FE↔BE', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    paperStoreState.currentPaper = {
      paper_id: 'hss-001',
      title: '测试论文',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
    paperStoreState.currentGraph = {
      paper_id: 'hss-001',
      paradigm: 'HSS',
      nodes: [{ id: 'n1', label: '核心论点', type: 'Thesis', data: {} }],
      edges: [],
    }
    paperStoreState.fetchDetail.mockResolvedValue(undefined)
    paperStoreState.fetchGraph.mockResolvedValue(undefined)
    mockListPapers.mockResolvedValue({
      data: {
        items: [
          { paper_id: 'hss-001', title: 'A', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:00:00Z' },
          { paper_id: 'hss-002', title: 'B', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:10:00Z' },
        ],
        total: 2,
        offset: 0,
        limit: 20,
      },
      meta: { request_id: 'robust' },
    })
  })

  describe('A-05 QA SSE — parser ↔ BE error codes', () => {
    it('red: GRAPH_NOT_FOUND SSE maps to user-facing message for detail view', () => {
      const parsed = parseQaStreamEvent(
        'error',
        JSON.stringify({
          code: 'GRAPH_NOT_FOUND',
          message: '论文 hss-002 的图谱尚未建好，请等待流水线完成。',
        }),
      )
      expect(parsed?.type).toBe('error')
      if (parsed?.type === 'error') {
        expect(parsed.data.code).toBe('GRAPH_NOT_FOUND')
        expect(parsed.data.message).toContain('图谱尚未建好')
      }
    })

    it('red: QA_STREAM_ERROR preserves code for diagnostics', () => {
      const parsed = parseQaStreamEvent('error', JSON.stringify({ code: 'QA_STREAM_ERROR', message: 'LLM 调用失败' }))
      expect(parsed?.type).toBe('error')
      if (parsed?.type === 'error') {
        expect(parsed.data.code).toBe('QA_STREAM_ERROR')
        expect(parsed.data.message).toBe('LLM 调用失败')
      }
    })
  })

  describe('A-05 PaperDetailView — usable QA + red feedback', () => {
    it('boundary: whitespace-only question does not call streamPaperQa', async () => {
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

    it('green: trimmed question is sent to streamPaperQa', async () => {
      mockStreamPaperQa.mockResolvedValue(undefined)
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-001' },
        global: { stubs: detailStubs },
      })
      await flushPromises()

      await wrapper.find('.qa-textarea').setValue('  核心论点？  ')
      await wrapper
        .findAll('button')
        .find((button) => button.text() === '提问')
        ?.trigger('click')
      await flushPromises()

      expect(mockStreamPaperQa).toHaveBeenCalledWith(
        'hss-001',
        '核心论点？',
        expect.any(Object),
        expect.any(AbortSignal),
      )
    })

    it('red: SSE onError surfaces prefixed message in answer panel', async () => {
      mockStreamPaperQa.mockImplementation(
        async (_paperId: string, _question: string, handlers: { onError?: (message: string) => void }) => {
          handlers.onError?.('论文 hss-002 的图谱尚未建好，请等待流水线完成。')
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

      expect(wrapper.find('.detail-qa__answer-text').text()).toBe(
        '错误: 论文 hss-002 的图谱尚未建好，请等待流水线完成。',
      )
    })

    it('red: processing paper shows not-ready alert and disables QA controls', async () => {
      paperStoreState.currentPaper = {
        ...paperStoreState.currentPaper,
        status: 'processing',
      }
      paperStoreState.currentGraph = null

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-002' },
        global: { stubs: detailStubs },
      })
      await flushPromises()

      expect(wrapper.find('.detail-alert-stub').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
      expect((wrapper.find('.qa-textarea').element as HTMLTextAreaElement).disabled).toBe(true)
      const askButton = wrapper.findAll('button').find((button) => button.text() === '提问')
      expect((askButton?.element as HTMLButtonElement).disabled).toBe(true)
    })

    it('green: citation click updates highlight before full-graph navigation', async () => {
      mockStreamPaperQa.mockImplementation(
        async (
          _paperId: string,
          _question: string,
          handlers: {
            onCitation?: (data: QaStreamCitationData) => void
            onDone?: (data: { answer_id: string }) => void
          },
        ) => {
          handlers.onCitation?.({ type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' })
          handlers.onDone?.({ answer_id: 'ans-1' })
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

      await wrapper.find('.citation-tag').trigger('click')
      expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe('n1')

      await wrapper
        .findAll('button')
        .find((button) => button.text().includes('全屏图谱'))
        ?.trigger('click')

      expect(mockPush).toHaveBeenCalledWith({
        name: RouteName.PaperGraph,
        params: { paperId: 'hss-001' },
        query: { node: 'n1' },
      })
    })
  })

  describe('A-07 / A-08 — pipeline failure feedback (FE status contract)', () => {
    it('red: failed status fixture exposes error_code and human message for detail UI', () => {
      const data = failedStatusFixture.data as PaperStatusData
      expect(isFailedStatus(data)).toBe(true)
      expect(data.error_code).toBe('LLM_JSON_INVALID')
      expect(data.message.length).toBeGreaterThan(0)
    })

    it('red: failed paper disables QA like processing', async () => {
      paperStoreState.currentPaper = {
        paper_id: 'hss-failed-001',
        title: '失败论文',
        status: 'failed',
        paradigm: 'HSS',
        created_at: '2026-05-19T10:00:00Z',
      }
      paperStoreState.currentGraph = null

      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-failed-001' },
        global: { stubs: detailStubs },
      })
      await flushPromises()

      expect(wrapper.find('.detail-alert-stub').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
      expect(mockStreamPaperQa).not.toHaveBeenCalled()
    })
  })

  describe('A-06 PatrolView — client validation before API', () => {
    it('boundary: duplicate paper ids blocked with validation copy', () => {
      expect(validatePatrolSelection('hss-001', 'hss-001')).toBe(PATROL_BASELINE_COPY.validationDuplicate('hss-001'))
      expect(validatePatrolPaperIds(['hss-001', 'hss-001'])).toContain('hss-001')
    })

    it('boundary: empty paper id selection fails client validation', () => {
      expect(validatePatrolSelection('', 'hss-002')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
      expect(validatePatrolSelection('hss-001', '')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
      expect(validatePatrolPaperIds(['hss-001'])).toBe(PATROL_BASELINE_COPY.validationExactTwo)
    })

    it('red: PATROL_INSUFFICIENT_DATA maps reset-selection CTA', () => {
      const presentation = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '未找到可比较的节点')
      expect(presentation.ctaKind).toBe('reset-selection')
      expect(presentation.description).toBeTruthy()
    })

    it('red: GRAPH_NOT_READY maps papers CTA for navigation', () => {
      const presentation = resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪')
      expect(presentation.ctaKind).toBe('papers')
      expect(presentation.ctaLabel).toBe(PATROL_BASELINE_COPY.graphNotReadyCta)
    })
  })
})
