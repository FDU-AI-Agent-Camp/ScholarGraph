/**
 * G1 — Papers list «图谱» gate unlocks ready_with_warnings (runtime render).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperSummary } from '@/api/types'
import { RouteName } from '@/router/meta'
import PapersView from '@/views/PapersView.vue'

const push = vi.fn()
const fetchList = vi.fn().mockResolvedValue(undefined)

const rwwRow: PaperSummary = {
  paper_id: 'stem-rww',
  title: 'RWW Paper',
  paradigm: 'STEM',
  status: 'ready_with_warnings',
  created_at: '2026-05-19T10:00:00Z',
}

const processingRow: PaperSummary = {
  paper_id: 'hss-proc',
  title: 'Processing',
  paradigm: 'HSS',
  status: 'processing',
  created_at: '2026-05-19T10:10:00Z',
}

const paperStoreState = {
  items: [rwwRow, processingRow] as PaperSummary[],
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

/**
 * Renders Action column slot bodies against each table row — production v-if is evaluated.
 */
const actionTableStubs = {
  PaperUpload: true,
  BadgeParadigm: true,
  BadgeStatus: true,
  EmptyState: true,
  'el-icon': true,
  'el-button': {
    props: ['link', 'type', 'disabled'],
    template: '<button type="button" :disabled="disabled"><slot /></button>',
  },
  'el-table': {
    props: ['data'],
    template: '<div class="table-stub"><slot /></div>',
  },
  'el-table-column': {
    props: ['label', 'prop', 'width', 'minWidth'],
    setup(
      _props: Record<string, unknown>,
      context: {
        slots: { default?: (slotProps: { row: PaperSummary }) => unknown }
      },
    ) {
      return () => {
        const rows = paperStoreState.items
        if (!context.slots.default) {
          return null
        }
        return rows.map((row) => context.slots.default?.({ row }))
      }
    },
  },
}

describe('PapersView G1 graph entry', () => {
  beforeEach(() => {
    push.mockReset()
    fetchList.mockClear()
    paperStoreState.items = [rwwRow, processingRow]
    paperStoreState.loading = false
  })

  it('test_list_page_action_for_rww — shows 图谱 enabled and routes to graph', async () => {
    const wrapper = mount(PapersView, {
      global: { stubs: actionTableStubs },
    })
    await flushPromises()

    const graphButtons = wrapper.findAll('button').filter((node) => node.text().includes('图谱'))
    expect(graphButtons).toHaveLength(1)
    expect((graphButtons[0]?.element as HTMLButtonElement).disabled).toBe(false)

    await graphButtons[0]?.trigger('click')
    expect(push).toHaveBeenCalledWith({
      name: RouteName.PaperGraph,
      params: { paperId: 'stem-rww' },
    })
  })

  it('hides 图谱 for processing rows (越权 negative)', async () => {
    paperStoreState.items = [processingRow]
    const wrapper = mount(PapersView, {
      global: { stubs: actionTableStubs },
    })
    await flushPromises()

    const graphButtons = wrapper.findAll('button').filter((node) => node.text().includes('图谱'))
    expect(graphButtons).toHaveLength(0)
  })
})
