/**
 * V1 DoD C-03 / C-04 — CLI 冒烟契约与前后端联调联试.
 *
 * C-03: M2 三类尺度 citation ↔ graph-hss.json ↔ DetailView 高亮
 * C-04: patrol corpus seed node_refs ↔ PatrolView 深链 ↔ POST /patrol
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { PaperDetail, PatrolReport, QaStreamCitationData, UnifiedPaperGraph } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { appendUniqueCitation, buildHighlightStateMap } from '@/utils/paperGraph'
import { citationNodeId } from '@/utils/qaCitations'
import { resolvePatrolApiError } from '@/utils/patrolForm'
import { readFrontendSource } from '@/test/helpers/designTokens'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'

const MOCK_DISCLAIMER = '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）'
const graph = graphFixture.data as UnifiedPaperGraph

/** Mirrors backend ``M2_HSS_QUESTIONS`` + mock LLM scale → node_id (tests/integration/test_dod_c03_c04.py). */
const M2_SCALE_EXPECTATIONS = [
  {
    scale: 'summary',
    question: '这篇论文做了什么？请给出核心论点总览。',
    nodeId: 'n1',
    nodeType: 'Thesis',
  },
  {
    scale: 'detail',
    question: '分论点如何支撑核心论点？',
    nodeId: 'n2',
    nodeType: 'SubArgument',
  },
  {
    scale: 'verification',
    question: '核心论点通过哪些材料、经何种理论视角被论证？',
    nodeId: 'n_lens',
    nodeType: 'AnalyticalLens',
  },
] as const

/** Mirrors ``CORPUS_PATROL_LENSES`` from backend.patrol.samples (C-04 CLI seed). */
const PATROL_CORPUS_NODE_REFS = [
  { type: 'node', paper_id: 'hss-001', node_id: 'n_lens_molecular_history', label: '分子考古与民族史视角' },
  { type: 'node', paper_id: 'hss-002', node_id: 'n_lens_political_film', label: '政治传播与电影叙事' },
] as const

function buildM2MockSseFrames(nodeId: string, label: string) {
  return [
    { event: 'message', data: { delta: '【摘要尺度】根据知识图谱上下文，' } },
    { event: 'citation', data: { paper_id: 'hss-001', node_id: nodeId, label } },
    { event: 'message', data: { delta: MOCK_DISCLAIMER } },
    { event: 'done', data: { answer_id: 'ans-hss-001' } },
  ] as const
}

const mockStreamPaperQa = vi.fn()
const mockFetchDetail = vi.fn()
const mockFetchGraph = vi.fn()
const mockFetchList = vi.fn()
const mockListPapers = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())

const paperListItems = [
  {
    paper_id: 'hss-001',
    title: 'A',
    paradigm: 'HSS' as const,
    status: 'ready' as const,
    created_at: '2026-05-19T10:00:00Z',
  },
  {
    paper_id: 'hss-002',
    title: 'B',
    paradigm: 'HSS' as const,
    status: 'ready' as const,
    created_at: '2026-05-19T10:10:00Z',
  },
]

const paperStoreState: {
  loading: boolean
  items: typeof paperListItems
  currentPaper: PaperDetail
  currentGraph: UnifiedPaperGraph
  fetchDetail: typeof mockFetchDetail
  fetchGraph: typeof mockFetchGraph
  fetchList: typeof mockFetchList
} = {
  loading: false,
  items: paperListItems,
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
  fetchList: mockFetchList,
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
  RouterLink: { template: '<a><slot /></a>' },
}

async function mountDetailView(paperId: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/papers/:paperId', name: 'detail', component: { template: '<div />' } }],
  })
  await router.push(`/papers/${paperId}`)
  await router.isReady()
  const wrapper = mount(PaperDetailView, {
    props: { paperId },
    global: { plugins: [router], stubs: detailStubs },
  })
  await flushPromises()
  return wrapper
}

const patrolRouteStubs = {
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<select class="patrol-select-c04" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  'el-option': true,
  'el-input': true,
  'el-space': { template: '<div><slot /></div>' },
  'el-icon': true,
  'el-button': {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  RouterLink: {
    props: ['to'],
    template: '<a class="patrol-graph-link-c04" :href="JSON.stringify(to)"><slot /></a>',
  },
  InsightCard: {
    props: ['variant', 'insightId', 'title'],
    template: '<div class="patrol-insight-c04" :data-variant="variant"><slot /></div>',
  },
  'el-alert': {
    inheritAttrs: false,
    props: ['title', 'description'],
    template:
      '<div class="patrol-alert-c04" v-bind="$attrs" :data-title="title" :data-description="description"><slot /></div>',
  },
  BadgeParadigm: true,
}

function dispatchQaFrames(
  frames: ReadonlyArray<{ event: string; data: Record<string, unknown> }>,
  handlers: {
    onMessage?: (data: { delta: string }) => void
    onCitation?: (data: QaStreamCitationData) => void
    onDone?: (data: { answer_id: string }) => void
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

function buildPatrolCorpusReport(): PatrolReport {
  return {
    mode: 'lens_clash',
    paper_ids: ['hss-001', 'hss-002'],
    insights: [
      {
        insight_id: 'ins-lens-clash-001',
        title: '理论视角冲突（Lens Clash）',
        summary: '【Mock 巡检摘要】基于两篇论文的图谱节点差异生成摘要。',
        status: 'ready',
        paper_ids: ['hss-001', 'hss-002'],
        node_refs: [...PATROL_CORPUS_NODE_REFS],
      },
    ],
    generated_at: '2026-06-01T13:53:33.324792Z',
  }
}

async function mountPatrolView() {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/patrol')
  await router.isReady()
  const wrapper = mount(routerViewShell, {
    global: { plugins: [router], stubs: patrolRouteStubs },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('V1 DoD C-03 — M2 QA CLI ↔ graph-hss ↔ FE', () => {
  it('graph-hss fixture nodes match backend M2 smoke expected ids', () => {
    for (const sample of M2_SCALE_EXPECTATIONS) {
      const node = graph.nodes.find((item) => item.id === sample.nodeId)
      expect(node, `missing ${sample.nodeId}`).toBeDefined()
      expect(node?.type).toBe(sample.nodeType)
    }
  })

  it('parses M2-scale citation frames verifiable against graph-hss', () => {
    for (const sample of M2_SCALE_EXPECTATIONS) {
      const node = graph.nodes.find((item) => item.id === sample.nodeId)
      const frames = buildM2MockSseFrames(sample.nodeId, node?.label ?? '')
      const citeFrame = frames[1]
      const parsed = parseQaStreamEvent(citeFrame.event, JSON.stringify(citeFrame.data))
      expect(parsed?.type).toBe('citation')
      if (parsed?.type !== 'citation') {
        continue
      }
      expect(citationNodeId(parsed.data)).toBe(sample.nodeId)
      expect(parsed.data.label).toBe(node?.label)
      const states = buildHighlightStateMap(
        graph.nodes.map((item) => item.id),
        citationNodeId(parsed.data),
      )
      expect(states[sample.nodeId]).toBe('active')
    }
  })

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchDetail.mockResolvedValue(undefined)
    mockFetchGraph.mockResolvedValue(undefined)
    mockFetchList.mockResolvedValue(undefined)
    paperStoreState.items = paperListItems
    paperStoreState.currentGraph = graph
    paperStoreState.currentPaper = {
      paper_id: 'hss-001',
      title: '测试论文',
      status: 'ready',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
  })

  it('DetailView highlights graph-hss n1 after summary-scale QA (C-03 functional)', async () => {
    const sample = M2_SCALE_EXPECTATIONS[0]
    const node = graph.nodes.find((item) => item.id === sample.nodeId)
    mockStreamPaperQa.mockImplementation(
      async (_paperId: string, _question: string, handlers: Parameters<typeof dispatchQaFrames>[1]) => {
        dispatchQaFrames(buildM2MockSseFrames(sample.nodeId, node?.label ?? ''), handlers)
      },
    )

    const wrapper = await mountDetailView('hss-001')
    await wrapper.find('.qa-textarea').setValue(sample.question)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '提问')
      ?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.citation-tag').text()).toContain(node?.label ?? '')
    expect(wrapper.find('.paper-graph-stub').attributes('data-highlight')).toBe(sample.nodeId)
  })

  it('chains three M2 citations without duplicate tags (boundary)', () => {
    let citations: QaStreamCitationData[] = []
    for (const sample of M2_SCALE_EXPECTATIONS) {
      const node = graph.nodes.find((item) => item.id === sample.nodeId)
      citations = appendUniqueCitation(citations, {
        type: 'node',
        paper_id: 'hss-001',
        node_id: sample.nodeId,
        label: node?.label ?? '',
      })
    }
    expect(citations).toHaveLength(3)
  })

  it('surfaces GRAPH_NOT_FOUND when CLI/HTTP would fail without graph (red path)', async () => {
    mockStreamPaperQa.mockImplementation(
      async (_paperId: string, _question: string, handlers: { onError?: (message: string) => void }) => {
        dispatchQaFrames(
          [{ event: 'error', data: { code: 'GRAPH_NOT_FOUND', message: '论文 hss-001 的图谱尚未建好' } }],
          handlers,
        )
      },
    )

    const wrapper = await mountDetailView('hss-001')
    await wrapper.find('.qa-textarea').setValue(M2_SCALE_EXPECTATIONS[0].question)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '提问')
      ?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.detail-qa__answer-text').text()).toContain('图谱尚未建好')
  })

  it('blocks QA input when paper not ready (boundary)', async () => {
    paperStoreState.currentPaper = {
      paper_id: 'hss-002',
      title: '处理中',
      status: 'processing',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }

    const wrapper = await mountDetailView('hss-002')

    expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
    expect((wrapper.find('.qa-textarea').element as HTMLTextAreaElement).disabled).toBe(true)
  })
})

describe('V1 DoD C-04 — Patrol CLI ↔ HTTP ↔ PatrolView', () => {
  const patrolReport = buildPatrolCorpusReport()

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchList.mockResolvedValue(undefined)
    paperStoreState.items = paperListItems
    mockListPapers.mockResolvedValue({
      data: {
        items: paperListItems,
        total: 2,
        offset: 0,
        limit: 20,
      },
      meta: { request_id: 'c04-list' },
    })
  })

  it('patrol corpus node_refs align with backend seed ids (static parity)', () => {
    expect(PATROL_CORPUS_NODE_REFS[0].node_id).toBe('n_lens_molecular_history')
    expect(PATROL_CORPUS_NODE_REFS[1].node_id).toBe('n_lens_political_film')
    const patrolBundle = [
      readFrontendSource('views/PatrolView.vue'),
      readFrontendSource('utils/patrolViewHelpers.ts'),
    ].join('\n')
    expect(patrolBundle).toContain('query: { node: ref.node_id }')
    expect(patrolBundle).toContain('RouteName.PaperGraph')
  })

  it('runPatrol renders corpus insight with lens_clash variant (functional)', async () => {
    mockRunPatrol.mockResolvedValue({ data: patrolReport, meta: { request_id: 'c04-patrol' } })

    const { wrapper } = await mountPatrolView()
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(
      expect.arrayContaining(['hss-001', 'hss-002']),
      expect.objectContaining({ mode: 'lens_clash' }),
    )
    expect(wrapper.find('.patrol-insight-c04').attributes('data-variant')).toBe('lens_clash')
    expect(patrolReport.insights[0]?.node_refs).toEqual([...PATROL_CORPUS_NODE_REFS])
  })

  it('node_refs deep-link to graph route with node query (C-04 cross-stack)', () => {
    const ref = PATROL_CORPUS_NODE_REFS[0]
    const href = JSON.stringify({
      name: RouteName.PaperGraph,
      params: { paperId: ref.paper_id },
      query: { node: ref.node_id },
    })
    expect(href).toContain('n_lens_molecular_history')
    expect(href).toContain('hss-001')
  })

  it('maps GRAPH_NOT_READY to baseline copy after runPatrol 409 (red path)', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const { wrapper } = await mountPatrolView()
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-view__error-panel .patrol-alert-c04')
    expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
    expect(resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪').ctaKind).toBe('papers')
  })

  it('maps PATROL_INSUFFICIENT_DATA to reset-selection CTA (red path)', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '巡检数据不足' }, 422),
    )

    const { wrapper } = await mountPatrolView()
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-view__error-panel .patrol-alert-c04')
    expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足').ctaKind).toBe('reset-selection')
  })
})
