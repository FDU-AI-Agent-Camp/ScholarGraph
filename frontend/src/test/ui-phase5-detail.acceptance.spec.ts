/**
 * Phase 5 Detail acceptance (5.1–5.10) — design-spec §9 + ui-design-progress §1.4.
 */
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperDetail } from '@/api/types'
import PaperMetadataCard from '@/components/papers/PaperMetadataCard.vue'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { PIPELINE_STEPS } from '@/utils/pipelineSteps'
import { processingStatus } from '@/test/fixtures/paperStatus'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import PaperDetailView from '@/views/PaperDetailView.vue'

const detailViewSrc = readFrontendSource('views/PaperDetailView.vue')
const statusPanelSrc = readFrontendSource('components/papers/PaperStatusPanel.vue')
const metadataCardSrc = readFrontendSource('components/papers/PaperMetadataCard.vue')
const detailCopySrc = readFrontendSource('constants/detailCopy.ts')
const pipelineStepsSrc = readFrontendSource('utils/pipelineSteps.ts')
const paperGraphSrc = readFrontendSource('utils/paperGraph.ts')
const paperGraphComponentSrc = readFrontendSource('components/graph/PaperGraph.vue')
const graphLegendSrc = readFrontendSource('components/graph/GraphLegend.vue')
const tagCitationSrc = readFrontendSource('components/ui/TagCitation.vue')
const badgeStatusSrc = readFrontendSource('components/ui/BadgeStatus.vue')

const mockFetchDetail = vi.fn()
const mockFetchGraph = vi.fn()

const paperStoreState: {
  loading: boolean
  currentPaper: PaperDetail | null
  currentGraph: null
  fetchDetail: typeof mockFetchDetail
  fetchGraph: typeof mockFetchGraph
} = {
  loading: false,
  currentPaper: null,
  currentGraph: null,
  fetchDetail: mockFetchDetail,
  fetchGraph: mockFetchGraph,
}

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-stub"><slot /></a>',
  },
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

vi.mock('@/composables/usePaperStatus', () => ({
  usePaperStatus: () => ({
    status: ref(processingStatus),
    polling: ref(true),
    start: vi.fn(),
    stop: vi.fn(),
    pollOnce: vi.fn(),
  }),
}))

const detailViewStubs = {
  PaperGraph: true,
  PaperMetadataCard: true,
  PaperStatusPanel: true,
  BadgeParadigm: true,
  BadgeStatus: true,
  'el-input': {
    props: ['disabled'],
    template: '<textarea class="qa-textarea" :disabled="disabled" />',
  },
  'el-button': { template: '<button :disabled="disabled"><slot /></button>', props: ['disabled'] },
  'el-space': { template: '<div><slot /></div>' },
  'el-card': true,
  TagCitation: true,
  'el-alert': {
    props: ['title'],
    template: '<div class="detail-qa__alert" :data-title="title" />',
  },
}

describe('Phase 5 Detail acceptance (5.1–5.10)', () => {
  beforeEach(() => {
    mockFetchDetail.mockReset()
    mockFetchGraph.mockReset()
    mockFetchDetail.mockResolvedValue(undefined)
    mockFetchGraph.mockResolvedValue(undefined)
    paperStoreState.currentPaper = {
      paper_id: 'hss-002',
      title: '处理中论文',
      status: 'processing',
      paradigm: 'HSS',
      created_at: '2026-05-19T10:00:00Z',
    }
  })

  describe('checklist: PaperDetailView.spec + PaperStatusPanel regression gate', () => {
    it('PaperDetailView mounts processing frame with baseline not-ready alert', async () => {
      const wrapper = mount(PaperDetailView, {
        props: { paperId: 'hss-002' },
        global: { stubs: detailViewStubs },
      })

      await flushPromises()

      expect(wrapper.find('.detail-layout').exists()).toBe(true)
      expect(wrapper.find('.detail-qa__alert').attributes('data-title')).toBe(DETAIL_BASELINE_COPY.notReadyAlert)
    })

    it('PaperStatusPanel mounts with pipeline title and refresh caption', () => {
      const wrapper = mount(PaperStatusPanel, {
        props: { paperId: 'paper-001', autoStart: false },
        global: {
          stubs: {
            'el-progress': true,
            'el-alert': true,
            'el-button': true,
          },
        },
      })

      expect(wrapper.find('.status-panel__title').text()).toBe(DETAIL_BASELINE_COPY.pipelineTitle)
      expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.refreshCaption)
    })
  })

  describe('5.1 dual-column layout ≥1024px, gap 24, module order', () => {
    it('PaperDetailView defines 45/55 grid and left-column module stack', () => {
      expect(detailViewSrc).toContain('grid-template-columns: 45fr 55fr')
      expect(detailViewSrc).toContain('gap: var(--spacing-24)')
      expect(detailViewSrc).toContain('PaperMetadataCard')
      expect(detailViewSrc).toContain('PaperStatusPanel')
      expect(detailViewSrc.indexOf('PaperMetadataCard')).toBeLessThan(detailViewSrc.indexOf('PaperStatusPanel'))
      expect(detailViewSrc.indexOf('PaperStatusPanel')).toBeLessThan(detailViewSrc.indexOf('detail-qa'))
      expect(detailViewSrc).toContain('detail-graph')
    })
  })

  describe('5.2 header back link, 2-line title, meta badges', () => {
    it('uses baseline back copy, line-clamp title, and Badge components', () => {
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.backLink)
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY.backLink')
      expect(detailViewSrc).toContain('-webkit-line-clamp: 2')
      expect(detailViewSrc).toContain('<BadgeParadigm')
      expect(detailViewSrc).toContain('<BadgeStatus')
      expect(detailViewSrc).toContain('detail-header__paper-id')
    })
  })

  describe('5.3 collapsible metadata card with classification reason toggle', () => {
    it('PaperMetadataCard exposes collapse and reason toggle copy', () => {
      expect(metadataCardSrc).toContain('el-collapse')
      expect(metadataCardSrc).toContain('DETAIL_BASELINE_COPY.metadataTitle')
      expect(metadataCardSrc).toContain('DETAIL_BASELINE_COPY.showClassificationReason')
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.showClassificationReason)
      expect(metadataCardSrc).toContain('classification.reason')
    })

    it('mounts metadata card with baseline toggle label', () => {
      const wrapper = mount(PaperMetadataCard, {
        props: {
          classification: {
            paradigm: 'HSS',
            confidence: 0.9,
            reason: '测试分类依据',
          },
        },
        global: {
          stubs: {
            'el-collapse': { template: '<div><slot /></div>' },
            'el-collapse-item': {
              props: ['title'],
              template: '<div><span class="collapse-title">{{ title }}</span><slot /></div>',
            },
            'el-progress': true,
            BadgeParadigm: true,
          },
        },
      })

      expect(wrapper.find('.metadata-card__reason-toggle').text()).toBe(DETAIL_BASELINE_COPY.showClassificationReason)
    })
  })

  describe('checklist: §1.4.4 Step / Alert baseline copy', () => {
    it('detailCopy and pipelineSteps align with ui-design-progress baseline table', () => {
      expect(detailCopySrc).toContain('论文尚未 ready，问答与图谱预览将在流水线完成后可用。')
      expect(detailCopySrc).toContain('每 2 秒自动刷新')
      expect(detailCopySrc).toContain('暂停自动刷新')
      expect(detailCopySrc).toContain('继续自动刷新')
      expect(statusPanelSrc).not.toContain('轮询')
      for (const step of PIPELINE_STEPS) {
        expect(pipelineStepsSrc).toContain(step.label)
      }
    })
  })

  describe('5.4 stepper, 8px progress, refresh caption', () => {
    it('PaperStatusPanel wires pipeline steps and progress styling', () => {
      for (const step of PIPELINE_STEPS) {
        expect(pipelineStepsSrc).toContain(step.label)
      }
      expect(statusPanelSrc).toContain('PIPELINE_STEPS')
      expect(statusPanelSrc).toContain(':stroke-width="8"')
      expect(statusPanelSrc).toContain('var(--color-primary-light)')
      expect(statusPanelSrc).toContain('PIPELINE_REFRESH_CAPTION')
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.refreshCaption)
      expect(statusPanelSrc).toContain('status-panel__steps')
    })
  })

  describe('5.5 not-ready Info Alert baseline', () => {
    it('PaperDetailView binds baseline alert copy for non-ready papers', () => {
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.notReadyAlert)
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY.notReadyAlert')
      expect(detailViewSrc).toContain(':disabled="!isReady()"')
    })
  })

  describe('5.6 QA placeholder and answer panel styling', () => {
    it('uses baseline placeholder and subtle answer panel with body-lg', () => {
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.qaPlaceholder)
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY.qaPlaceholder')
      expect(detailViewSrc).toContain('detail-qa__answer-panel')
      expect(detailViewSrc).toContain('text-body-lg')
      expect(detailViewSrc).toContain('var(--color-bg-subtle)')
    })
  })

  describe('5.7 SSE streaming cursor', () => {
    it('renders accent blinking pipe cursor while streaming', () => {
      expect(detailViewSrc).toContain('detail-qa__cursor')
      expect(detailViewSrc).toContain('var(--color-primary)')
      expect(detailViewSrc).toContain('detail-qa-cursor-blink')
      expect(detailViewSrc).toContain('var(--duration-blink)')
    })
  })

  describe('5.8 TagCitation 150ms active sync with highlightNodeId', () => {
    it('wires citation tags to highlightNodeId with fast transition token', () => {
      expect(detailViewSrc).toContain(':active="item.node_id === highlightNodeId"')
      expect(detailViewSrc).toContain('@node-click="onGraphNodeClick"')
      expect(detailViewSrc).toContain('@click="focusCitation(item)"')
      expect(tagCitationSrc).toContain('var(--transition-fast)')
    })
  })

  describe('5.9 compact graph canvas and legend overlay', () => {
    it('PaperGraph compact mode uses canvas background and floating legend', () => {
      expect(paperGraphComponentSrc).toContain('GraphLegend')
      expect(paperGraphComponentSrc).toContain('var(--color-bg-canvas)')
      expect(paperGraphComponentSrc).toContain('paper-graph__legend')
      expect(graphLegendSrc).toContain('GRAPH_BASELINE_COPY.legendTitle')
      expect(paperGraphSrc).toContain('listGraphLegendEntries')
      expect(detailViewSrc).toContain('detail-graph__canvas')
      expect(detailViewSrc).toContain(':graph="paperStore.currentGraph"')
      expect(detailViewSrc).toContain('compact')
    })

    it('§17 Detail compact height uses GRAPH_COMPACT_HEIGHT = 320', () => {
      expect(paperGraphSrc).toContain('GRAPH_COMPACT_HEIGHT = 320')
      expect(paperGraphComponentSrc).toContain('GRAPH_COMPACT_HEIGHT')
      expect(paperGraphComponentSrc).toContain('min-height: 320px')
      expect(detailViewSrc).toContain('min-height: 320px')
    })
  })

  describe('5.10 processing pulse and step done check animation', () => {
    it('BadgeStatus processing dot pulses and done steps animate check at 250ms', () => {
      expect(badgeStatusSrc).toContain('badge-status-pulse')
      expect(badgeStatusSrc).toContain('var(--duration-pulse)')
      expect(statusPanelSrc).toContain('status-step-check-in')
      expect(statusPanelSrc).toContain('var(--duration-slow)')
      expect(statusPanelSrc).toContain('status-step-pulse')
    })
  })

  describe('Phase 5 acceptance checklist (ui-design-progress §验收)', () => {
    it('§1.4.2: dual-column 45/55 grid and left-column module order', () => {
      expect(detailViewSrc).toContain('grid-template-columns: 45fr 55fr')
      expect(detailViewSrc.indexOf('PaperMetadataCard')).toBeLessThan(detailViewSrc.indexOf('PaperStatusPanel'))
      expect(detailViewSrc.indexOf('PaperStatusPanel')).toBeLessThan(detailViewSrc.indexOf('detail-qa'))
      expect(detailViewSrc).toContain('detail-graph')
    })

    it('§1.4.4: Step labels, not-ready Alert, and refresh caption match baseline table', () => {
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.notReadyAlert)
      expect(detailCopySrc).toContain(DETAIL_BASELINE_COPY.refreshCaption)
      for (const step of PIPELINE_STEPS) {
        expect(pipelineStepsSrc).toContain(step.label)
      }
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY.notReadyAlert')
    })

    it('§1.4.1 (5.6): answer panel uses subtle #FAFBFC surface inside QA card', () => {
      const tokens = loadDesignTokenMap()

      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(detailViewSrc).toContain('detail-qa__answer-panel')
      expect(detailViewSrc).toContain('var(--color-bg-subtle)')
      expect(detailViewSrc).toContain('text-body-lg')
    })

    it('§1.4.3 (5.8): TagCitation active sync and graph highlight share highlightNodeId with 150ms token', () => {
      const tokens = loadDesignTokenMap()

      expect(tokens['--duration-fast']).toBe('150ms')
      expect(detailViewSrc).toContain(':active="item.node_id === highlightNodeId"')
      expect(detailViewSrc).toContain('@node-click="onGraphNodeClick"')
      expect(detailViewSrc).toContain('@click="focusCitation(item)"')
      expect(tagCitationSrc).toContain('var(--transition-fast)')
    })

    it('regression gate: PaperDetailView.spec and graph-qa.integration cover QA answer + citation chain', () => {
      const detailSpecSrc = readFrontendSource('views/PaperDetailView.spec.ts')
      const graphQaSrc = readFrontendSource('test/graph-qa.integration.test.ts')

      expect(detailSpecSrc).toContain('detail-qa__answer-panel')
      expect(detailSpecSrc).toContain('§1.4.3 citation ↔ graph highlight (5.8)')
      expect(detailSpecSrc).toContain('§1.4.1 subtle surface token')
      expect(graphQaSrc).toContain('chains SSE citation event into highlight state')
      expect(graphQaSrc).toContain('switches graph highlight when user selects another cited node')
      expect(graphQaSrc).toContain('maps Detail answer panel to §1.4.1 subtle surface token')
    })
  })
})
