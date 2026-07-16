/**
 * Detail delete chaos — stale store snapshot vs live pre-flight status.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperDetail } from '@/api/types'
import { PAPER_DELETE_COPY } from '@/utils/paperDelete'
import PaperDetailView from '@/views/PaperDetailView.vue'

const mockFetchDetail = vi.fn()
const mockFetchGraph = vi.fn()
const mockPush = vi.fn()
const mockClearCurrent = vi.fn()
const confirm = vi.fn()
const deletePaper = vi.fn()
const getPaperStatus = vi.fn()

const failedPaper: PaperDetail = {
  paper_id: 'hss-failed-001',
  title: 'Store 仍显示 failed',
  status: 'failed',
  paradigm: 'HSS',
  created_at: '2026-05-19T10:00:00Z',
}

const paperStoreState = reactive({
  loading: false,
  currentPaper: failedPaper,
  currentGraph: null,
  fetchDetail: mockFetchDetail,
  fetchGraph: mockFetchGraph,
  clearCurrent: mockClearCurrent,
})

vi.mock('@/api/qaStream', () => ({
  streamPaperQa: vi.fn(),
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

vi.mock('@/api/papers', () => ({
  getPaperStatus: (...args: unknown[]) => getPaperStatus(...args),
  deletePaper: (...args: unknown[]) => deletePaper(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: {
    confirm: (...args: unknown[]) => confirm(...args),
    alert: vi.fn().mockResolvedValue(undefined),
  },
}))

const detailStubs = {
  PaperGraph: true,
  PaperMetadataCard: true,
  PaperStatusPanel: true,
  BadgeParadigm: true,
  BadgeStatus: true,
  TagCitation: true,
  'el-divider': true,
  'el-input': true,
  'el-button': {
    props: ['disabled', 'loading', 'type', 'plain', 'size', 'link', 'onClick'],
    template: '<button type="button" :disabled="disabled || loading" @click="onClick"><slot /></button>',
  },
  'el-space': { template: '<div><slot /></div>' },
  'el-alert': true,
}

describe('PaperDetailView delete integration', () => {
  beforeEach(() => {
    mockFetchDetail.mockReset().mockResolvedValue(undefined)
    mockFetchGraph.mockReset().mockResolvedValue(undefined)
    mockPush.mockReset()
    mockClearCurrent.mockReset()
    confirm.mockReset()
    deletePaper.mockReset()
    getPaperStatus.mockReset()
    paperStoreState.currentPaper = { ...failedPaper }
  })

  it('chaos: store failed but live status processing → force warn modal (not standard delete)', async () => {
    getPaperStatus.mockResolvedValue({
      data: {
        paper_id: 'hss-failed-001',
        status: 'processing',
        percent: 40,
        stage: 'extracting',
        message: 'extracting',
        updated_at: '2026-05-19T10:05:00Z',
      },
    })
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    const wrapper = mount(PaperDetailView, {
      props: { paperId: 'hss-failed-001' },
      global: { stubs: detailStubs },
    })
    await flushPromises()

    expect(paperStoreState.currentPaper.status).toBe('failed')

    await wrapper.get('[data-testid="detail-delete-button"]').trigger('click')
    await flushPromises()

    expect(getPaperStatus).toHaveBeenCalledWith('hss-failed-001')
    expect(confirm).toHaveBeenCalledTimes(1)
    const [message, title, options] = confirm.mock.calls[0] as [string, string, { confirmButtonText: string }]
    expect(message).toContain('提取内容或构建语义索引')
    expect(message).toContain('强行删除')
    expect(title).toBe(PAPER_DELETE_COPY.forceConfirmTitle)
    expect(options.confirmButtonText).toBe(PAPER_DELETE_COPY.forceConfirmOk)
    expect(confirm).not.toHaveBeenCalledWith(
      PAPER_DELETE_COPY.confirmMessage,
      PAPER_DELETE_COPY.confirmTitle,
      expect.anything(),
    )
    expect(deletePaper).toHaveBeenCalledWith('hss-failed-001', { force: true })
  })
})
