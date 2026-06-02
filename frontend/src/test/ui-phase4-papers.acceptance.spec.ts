/**
 * Phase 4 Papers acceptance — design-spec §8 + ui-design-progress §1.4.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperSummary } from '@/api/types'
import PaperUpload from '@/components/papers/PaperUpload.vue'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import { PAPERS_BASELINE_COPY } from '@/test/helpers/papersBaselineCopy'
import { createTableStripeCapture } from '@/test/helpers/tableStripeCaptureStub'
import PapersView from '@/views/PapersView.vue'

const papersViewSrc = readFrontendSource('views/PapersView.vue')
const paperUploadSrc = readFrontendSource('components/papers/PaperUpload.vue')

const push = vi.fn()
const fetchList = vi.fn().mockResolvedValue(undefined)

const paperStoreState = {
  items: [] as PaperSummary[],
  loading: false,
  fetchList,
}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

vi.mock('@/api/papers', () => ({
  uploadPaper: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

describe('Phase 4 Papers acceptance', () => {
  beforeEach(() => {
    paperStoreState.items = []
    paperStoreState.loading = false
    fetchList.mockClear()
  })

  describe('checklist: PapersView.spec.ts + PaperUpload.spec.ts regression gate', () => {
    it('PaperUpload mounts with upload zone structure and baseline tip', () => {
      const wrapper = mount(PaperUpload, {
        global: {
          stubs: {
            'el-upload': { template: '<div class="upload-stub" />' },
            'el-icon': true,
            'el-progress': true,
            'el-alert': true,
          },
        },
      })

      expect(wrapper.find('.paper-upload').exists()).toBe(true)
      expect(wrapper.find('.paper-upload__tip').text()).toBe(PAPERS_BASELINE_COPY.uploadTip)
    })

    it('PapersView mounts empty frame with baseline EmptyState copy', async () => {
      const wrapper = mount(PapersView, {
        global: {
          stubs: {
            PaperUpload: true,
            'el-table': true,
            'el-table-column': true,
            'el-button': { template: '<button><slot /></button>' },
            'el-icon': true,
          },
        },
      })

      await flushPromises()

      expect(wrapper.find('.papers-title').text()).toBe(PAPERS_BASELINE_COPY.title)
      expect(wrapper.find('.empty-state__title').text()).toBe(PAPERS_BASELINE_COPY.emptyTitle)
      expect(wrapper.find('.empty-state__body').text()).toBe(PAPERS_BASELINE_COPY.emptyBody)
    })
  })

  describe('checklist: §1.4.2 VISUAL_DENSITY — table page header, stripe, 52px row', () => {
    const tokens = loadDesignTokenMap()

    it('uses page and subtle background tokens for table header and stripe rows', () => {
      expect(tokens['--color-bg-page']).toBe('#f8f9fb')
      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(papersViewSrc).toContain('var(--color-bg-page)')
      expect(papersViewSrc).toContain('var(--color-bg-subtle)')
      expect(papersViewSrc).toContain('height: 52px')
    })

    it('enables el-table stripe and papers-table density class at runtime', () => {
      let stripe = false
      let tableClass = ''

      paperStoreState.items = [
        {
          paper_id: 'stem-001',
          title: 'Demo',
          paradigm: 'STEM',
          status: 'ready',
          created_at: '2026-05-19T10:00:00Z',
        },
      ]

      mount(PapersView, {
        global: {
          stubs: {
            PaperUpload: true,
            'el-table': createTableStripeCapture((state) => {
              stripe = state.stripe
              tableClass = state.tableClass
            }),
            'el-table-column': true,
            'el-button': true,
            'el-icon': true,
          },
        },
      })

      expect(stripe).toBe(true)
      expect(tableClass).toContain('papers-table')
      expect(papersViewSrc).toContain('margin-top: var(--spacing-32)')
    })
  })

  describe('checklist: §1.4.4 Upload / Empty baseline copy', () => {
    it('PaperUpload source and mount align with baseline table', () => {
      expect(paperUploadSrc).toContain('PAPERS_BASELINE_COPY')
      expect(PAPERS_BASELINE_COPY.uploadMain).toBe('拖拽 PDF 到此处，或')
      expect(PAPERS_BASELINE_COPY.uploadClick).toBe('点击上传')
      expect(PAPERS_BASELINE_COPY.uploadTip).toBe('建议 ≤32MB · 上传后自动进入解构流水线')
      expect(PAPERS_BASELINE_COPY.uploading).toBe('上传中…')
      expect(paperUploadSrc).not.toContain('上传后轮询 status')

      const wrapper = mount(PaperUpload, {
        global: {
          stubs: {
            'el-upload': { template: '<div />' },
            'el-icon': true,
            'el-progress': true,
            'el-alert': true,
          },
        },
      })

      expect(wrapper.find('.paper-upload__tip').text()).toBe(PAPERS_BASELINE_COPY.uploadTip)
    })

    it('PapersView page header and Empty frame use baseline copy only', () => {
      expect(papersViewSrc).toContain('PAPERS_BASELINE_COPY')
      expect(paperUploadSrc).toContain('PAPERS_BASELINE_COPY')
      expect(PAPERS_BASELINE_COPY.title).toBe('文献库')
      expect(PAPERS_BASELINE_COPY.subtitle).toBe('管理已上传论文，查看解构进度与图谱入口')
      expect(papersViewSrc).not.toContain('请输入')
      expect(papersViewSrc).not.toContain('Lorem')
    })
  })

  describe('§1.4.1 upload zone background layers', () => {
    it('uses subtle upload base and primary-light hover/drag states via tokens', () => {
      expect(paperUploadSrc).toContain('var(--color-bg-subtle)')
      expect(paperUploadSrc).toContain('var(--color-border-strong)')
      expect(paperUploadSrc).toContain('var(--color-primary-light)')
      expect(paperUploadSrc).toContain('.el-upload-dragger.is-dragover')
    })

    it('applies 120ms transitions on upload dragger (no transition: all)', () => {
      expect(paperUploadSrc).toContain('var(--transition-instant)')
      expect(paperUploadSrc).not.toContain('transition: all')
    })
  })

  describe('§8.6 frame requirements', () => {
    it('PaperUpload keeps inline error alert wiring for Upload-Error frame', () => {
      expect(paperUploadSrc).toContain('uploadError')
      expect(paperUploadSrc).toContain('el-alert')
    })

    it('PapersView wires EmptyState CTA toward upload section anchor', () => {
      expect(papersViewSrc).toContain('id="papers-upload"')
      expect(papersViewSrc).toContain('scrollToUpload')
    })
  })
})
