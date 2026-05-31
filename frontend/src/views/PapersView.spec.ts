import { defineComponent, h, unref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperSummary } from '@/api/types'
import { RouteName } from '@/router/meta'
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

describe('PapersView', () => {
  beforeEach(() => {
    push.mockReset()
    fetchList.mockClear()
    paperStoreState.items = [readyRow, processingRow]
    paperStoreState.loading = false
  })

  it('loads paper list on mount', async () => {
    mount(PapersView, {
      global: {
        stubs: {
          PaperUpload: true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()
    expect(fetchList).toHaveBeenCalled()
  })

  it('navigates to paper detail after upload', async () => {
    const wrapper = mount(PapersView, {
      global: {
        stubs: {
          PaperUpload: {
            template: '<button class="emit-upload" @click="$emit(\'uploaded\', \'new-paper\')">up</button>',
          },
          'el-table': true,
          'el-table-column': true,
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
          'el-table-column': true,
        },
      },
    })

    expect(tableRows).toHaveLength(2)
    expect(tableRows[0]?.status).toBe('ready')
    expect(tableRows.filter((row) => row.status === 'ready')).toHaveLength(1)
  })

  it('shows EmptyState baseline copy when paper list is empty', async () => {
    paperStoreState.items = []

    const wrapper = mount(PapersView, {
      global: {
        stubs: {
          PaperUpload: true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.empty-state__title').text()).toBe('还没有论文')
    expect(wrapper.find('.empty-state__body').text()).toBe('上传 PDF 开始自动解构')
    expect(wrapper.find('.table-stub').exists()).toBe(false)
  })
})
