import { defineComponent, h, unref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperSummary } from '@/api/types'
import { RouteName } from '@/router/meta'
import { PAPERS_BASELINE_COPY } from '@/test/helpers/papersBaselineCopy'
import { readFrontendSource } from '@/test/helpers/designTokens'
import PapersView from '@/views/PapersView.vue'

const push = vi.fn()
const fetchList = vi.fn().mockResolvedValue(undefined)

const readyRow: PaperSummary = {
  paper_id: 'hss-001',
  title: 'Ready 论文',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
}

const processingRow: PaperSummary = {
  paper_id: 'hss-002',
  title: 'Processing',
  paradigm: 'HSS',
  status: 'processing',
  created_at: '2026-05-19T10:10:00Z',
}

const paperStoreState = {
  items: [readyRow, processingRow] as PaperSummary[],
  loading: false,
  fetchList,
}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

const mockUploadPaper = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

const tableStubs = {
  'el-table-column': true,
  'el-button': { template: '<button><slot /></button>' },
  'el-icon': true,
}

describe('PapersView', () => {
  beforeEach(() => {
    push.mockReset()
    fetchList.mockClear()
    mockUploadPaper.mockReset()
    paperStoreState.items = [readyRow, processingRow]
    paperStoreState.loading = false
  })

  it('loads paper list on mount', async () => {
    mount(PapersView, {
      global: {
        stubs: {
          PaperUpload: true,
          'el-table': true,
          ...tableStubs,
        },
      },
    })
    await flushPromises()
    expect(fetchList).toHaveBeenCalled()
  })

  describe('§1.4.4 page header baseline copy', () => {
    it('renders H1, subtitle, and section titles from design-spec §8', () => {
      const wrapper = mount(PapersView, {
        global: {
          stubs: {
            PaperUpload: true,
            'el-table': true,
            ...tableStubs,
          },
        },
      })

      expect(wrapper.find('.papers-title').text()).toBe(PAPERS_BASELINE_COPY.title)
      expect(wrapper.find('.papers-subtitle').text()).toBe(PAPERS_BASELINE_COPY.subtitle)
      expect(wrapper.text()).toContain(PAPERS_BASELINE_COPY.uploadSection)
      expect(wrapper.text()).toContain(PAPERS_BASELINE_COPY.tableSection)
    })
  })

  describe('§1.4.2 high-density table', () => {
    it('binds stripe and papers-table class on el-table', () => {
      let stripe = false
      let tableClass = ''

      const TableCapture = defineComponent({
        props: {
          stripe: Boolean,
          class: [String, Array, Object],
          data: {
            type: Array,
            default: () => [],
          },
        },
        setup(props) {
          stripe = Boolean(props.stripe)
          tableClass = String(props.class ?? '')
          return () => h('div', { class: 'table-stub' })
        },
      })

      mount(PapersView, {
        global: {
          stubs: {
            PaperUpload: true,
            'el-table': TableCapture,
            ...tableStubs,
          },
        },
      })

      expect(stripe).toBe(true)
      expect(tableClass).toContain('papers-table')
    })

    it('wires BadgeStatus to row.status in table template', () => {
      const source = readFrontendSource('views/PapersView.vue')
      expect(source).toContain('<BadgeStatus :status="row.status" />')
      expect(source).toContain('label="状态"')
    })
  })

  it('navigates to paper detail after upload', async () => {
    const wrapper = mount(PapersView, {
      global: {
        stubs: {
          PaperUpload: {
            template: '<button class="emit-upload" @click="$emit(\'uploaded\', \'new-paper\')">up</button>',
          },
          'el-table': true,
          ...tableStubs,
        },
      },
    })
    await wrapper.find('.emit-upload').trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: RouteName.PaperDetail,
      params: { paperId: 'new-paper' },
    })
  })

  it('binds PaperSummary[] to table data', () => {
    let tableRows: PaperSummary[] = []
    const TableCapture = defineComponent({
      props: {
        data: {
          type: Array,
          default: () => [],
        },
      },
      setup(props) {
        tableRows = unref(props.data) as PaperSummary[]
        return () => h('div', { class: 'table-stub' })
      },
    })

    mount(PapersView, {
      global: {
        stubs: {
          PaperUpload: true,
          'el-table': TableCapture,
          ...tableStubs,
        },
      },
    })

    expect(tableRows).toHaveLength(2)
    expect(tableRows[0]?.status).toBe('ready')
    expect(tableRows.filter((row) => row.status === 'ready')).toHaveLength(1)
  })

  describe('§1.4.4 Empty baseline copy', () => {
    it('shows EmptyState baseline copy and upload CTA when paper list is empty', async () => {
      paperStoreState.items = []

      const wrapper = mount(PapersView, {
        global: {
          stubs: {
            PaperUpload: true,
            'el-table': true,
            ...tableStubs,
          },
        },
      })

      await flushPromises()

      expect(wrapper.find('.empty-state__title').text()).toBe(PAPERS_BASELINE_COPY.emptyTitle)
      expect(wrapper.find('.empty-state__body').text()).toBe(PAPERS_BASELINE_COPY.emptyBody)
      expect(wrapper.find('button').text()).toBe(PAPERS_BASELINE_COPY.emptyCta)
      expect(wrapper.find('.table-stub').exists()).toBe(false)
    })

    it('scrolls upload section into view when EmptyState CTA is clicked', async () => {
      paperStoreState.items = []
      const scrollIntoView = vi.fn()
      vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(scrollIntoView)

      const wrapper = mount(PapersView, {
        global: {
          stubs: {
            PaperUpload: true,
            'el-table': true,
            ...tableStubs,
          },
        },
      })

      await flushPromises()
      await wrapper.find('button').trigger('click')

      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
      expect(wrapper.find('#papers-upload').exists()).toBe(true)
    })
  })

  describe('PapersView + PaperUpload integration', () => {
    it('renders upload baseline copy from embedded PaperUpload', () => {
      mockUploadPaper.mockResolvedValue({ data: { paper_id: 'x', message: 'ok' } })

      const wrapper = mount(PapersView, {
        global: {
          stubs: {
            'el-table': true,
            'el-upload': {
              template: `
                <div class="upload-stub">
                  <p class="paper-upload__text">${PAPERS_BASELINE_COPY.uploadMain}<em>${PAPERS_BASELINE_COPY.uploadClick}</em></p>
                </div>
              `,
            },
            'el-progress': true,
            'el-alert': true,
            ...tableStubs,
          },
        },
      })

      expect(wrapper.find('.paper-upload__tip').text()).toBe(PAPERS_BASELINE_COPY.uploadTip)
      expect(wrapper.find('#papers-upload').exists()).toBe(true)
    })
  })
})
