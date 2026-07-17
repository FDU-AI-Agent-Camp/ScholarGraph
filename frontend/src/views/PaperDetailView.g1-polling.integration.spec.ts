/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * G1 Layer 3 — polling stop + detail rehydration when indexing → ready_with_warnings.
 * Vitest fake timers stand in for Playwright (no FE Playwright stack in this repo).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import * as papersApi from '@/api/papers'
import type { PaperDetail, PaperStatusData, UnifiedPaperGraph } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { RAG_INDEX_TIMEOUT_CODE, RAG_INDEX_TIMEOUT_MESSAGE } from '@/utils/extractWarnings'
import { indexingStatus, readyWithWarningsStatus, statusResponse } from '@/test/fixtures/paperStatus'
import PaperDetailView from '@/views/PaperDetailView.vue'

const mockFetchDetail = vi.fn().mockResolvedValue(undefined)
const mockFetchGraph = vi.fn().mockResolvedValue(undefined)
const mockPush = vi.fn()

const paperStoreState = reactive<{
  loading: boolean
  currentPaper: PaperDetail
  currentGraph: UnifiedPaperGraph | null
  fetchDetail: typeof mockFetchDetail
  fetchGraph: typeof mockFetchGraph
}>({
  loading: false,
  currentPaper: {
    paper_id: 'g1-poll-001',
    title: 'Indexing then RWW',
    status: 'indexing',
    paradigm: 'STEM',
    preview_available: false,
    created_at: '2026-05-19T10:00:00Z',
  },
  currentGraph: null,
  fetchDetail: mockFetchDetail,
  fetchGraph: mockFetchGraph,
})

vi.mock('@/api/papers', () => ({
  getPaperStatus: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-stub"><slot /></a>',
  },
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: vi.fn(),
}))

const indexingPayload: PaperStatusData = {
  ...indexingStatus,
  paper_id: 'g1-poll-001',
}

const rwwPayload: PaperStatusData = {
  ...readyWithWarningsStatus,
  paper_id: 'g1-poll-001',
  extract_warnings: [RAG_INDEX_TIMEOUT_CODE],
}

describe('G1 polling → RWW rehydration (integration)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockFetchDetail.mockClear()
    mockFetchGraph.mockClear()
    paperStoreState.currentPaper = {
      paper_id: 'g1-poll-001',
      title: 'Indexing then RWW',
      status: 'indexing',
      paradigm: 'STEM',
      preview_available: false,
      created_at: '2026-05-19T10:00:00Z',
    }
    paperStoreState.currentGraph = null

    let pollCount = 0
    vi.mocked(papersApi.getPaperStatus).mockImplementation(async () => {
      pollCount += 1
      if (pollCount < 3) {
        return statusResponse(indexingPayload)
      }
      return statusResponse(rwwPayload)
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('test_polling_stop_and_reload_on_rww — stops polls and rehydrates detail', async () => {
    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'g1-poll-001' },
      global: {
        stubs: {
          PaperGraph: { template: '<div class="paper-graph-stub" />' },
          PaperMetadataCard: true,
          BadgeParadigm: true,
          BadgeStatus: true,
          TagCitation: true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': { template: '<textarea class="qa-textarea" />' },
          'el-space': { template: '<div><slot /></div>' },
          'el-alert': {
            props: ['title', 'type', 'description'],
            template:
              '<div class="el-alert-stub" :data-title="title" :data-type="type" :data-description="description" />',
          },
          'el-progress': true,
          teleport: true,
        },
      },
    })

    await flushPromises()
    const fetchAfterMount = mockFetchDetail.mock.calls.length
    expect(papersApi.getPaperStatus).toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(wrapper.emitted()).toBeTruthy()
    const statusCallsAtTerminal = vi.mocked(papersApi.getPaperStatus).mock.calls.length
    expect(statusCallsAtTerminal).toBeGreaterThanOrEqual(3)
    expect(mockFetchDetail.mock.calls.length).toBeGreaterThan(fetchAfterMount)
    expect(mockFetchDetail).toHaveBeenCalledWith('g1-poll-001')

    await vi.advanceTimersByTimeAsync(10_000)
    await flushPromises()
    expect(vi.mocked(papersApi.getPaperStatus).mock.calls.length).toBe(statusCallsAtTerminal)

    paperStoreState.currentPaper = {
      ...paperStoreState.currentPaper,
      status: 'ready_with_warnings',
      extract_warnings: [RAG_INDEX_TIMEOUT_CODE],
      preview_available: true,
    }
    paperStoreState.currentGraph = {
      paper_id: 'g1-poll-001',
      paradigm: 'STEM',
      nodes: [{ id: 'n1', label: 'Method', type: 'Method', data: {} }],
      edges: [],
    }
    await flushPromises()

    expect(wrapper.find('.paper-graph-stub').exists()).toBe(true)
    expect(wrapper.find('.detail-qa__alert--mvp').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(DETAIL_BASELINE_COPY.mvpPreviewAlert.slice(0, 24))
    const warningAlert = wrapper
      .findAll('.el-alert-stub')
      .find((node) => node.attributes('data-title') === RAG_INDEX_TIMEOUT_MESSAGE)
    expect(warningAlert).toBeTruthy()

    wrapper.unmount()
  })
})
