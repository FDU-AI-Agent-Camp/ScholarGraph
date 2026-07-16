/**
 * Papers list delete UX boundary drill (Vitest/VTU).
 *
 * Locks row-level lock independence + 503 safety-block alert — same contracts a Playwright
 * multi-click script would assert; FE CI uses VTU (no Playwright app harness in package.json).
 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { PaperSummary } from '@/api/types'
import { PAPER_DELETE_COPY } from '@/utils/paperDelete'
import PapersView from '@/views/PapersView.vue'

const push = vi.fn()
const fetchList = vi.fn().mockResolvedValue(undefined)
const confirm = vi.fn()
const alert = vi.fn()
const errorToast = vi.fn()
const successToast = vi.fn()
const deletePaper = vi.fn()
const getPaperStatus = vi.fn()

const paperA: PaperSummary = {
  paper_id: 'paper-a',
  title: 'Paper A',
  paradigm: 'STEM',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
}

const paperB: PaperSummary = {
  paper_id: 'paper-b',
  title: 'Paper B',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:01:00Z',
}

const paperStoreState = {
  items: [paperA, paperB] as PaperSummary[],
  loading: false,
  fetchList,
}

vi.mock('@/composables/usePapersListActivePolling', () => ({
  usePapersListActivePolling: () => ({ sync: vi.fn(), stop: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

vi.mock('@/api/papers', () => ({
  uploadPaper: vi.fn(),
  deletePaper: (...args: unknown[]) => deletePaper(...args),
  getPaperStatus: (...args: unknown[]) => getPaperStatus(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: unknown[]) => successToast(...args),
    warning: vi.fn(),
    error: (...args: unknown[]) => errorToast(...args),
  },
  ElMessageBox: {
    confirm: (...args: unknown[]) => confirm(...args),
    alert: (...args: unknown[]) => alert(...args),
  },
}))

const actionTableStubs = {
  PaperUpload: true,
  BadgeParadigm: true,
  BadgeStatus: true,
  EmptyState: true,
  'el-icon': true,
  'el-button': {
    props: ['link', 'type', 'disabled', 'loading', 'onClick'],
    template:
      '<button type="button" :disabled="Boolean(disabled || loading)" :aria-busy="loading ? \'true\' : \'false\'" @click="onClick"><slot /></button>',
  },
  'el-table': {
    props: ['data', 'rowClassName'],
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

function deleteButton(wrapper: VueWrapper, paperId: string) {
  return wrapper.get(`[data-testid="papers-delete-button"][data-paper-id="${paperId}"]`)
}

describe('PapersView delete UX boundary', () => {
  beforeEach(() => {
    push.mockReset()
    fetchList.mockReset().mockResolvedValue(undefined)
    confirm.mockReset().mockResolvedValue(undefined)
    alert.mockReset().mockResolvedValue(undefined)
    errorToast.mockReset()
    successToast.mockReset()
    deletePaper.mockReset()
    getPaperStatus.mockReset()
    paperStoreState.items = [paperA, paperB]
    paperStoreState.loading = false
  })

  it('row-lock independence: while A DELETE is pending, B delete stays clickable and opens confirm', async () => {
    let releaseA: (() => void) | undefined
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    deletePaper.mockImplementation((paperId: string) => {
      if (paperId === 'paper-a') {
        return new Promise<void>((resolve) => {
          releaseA = resolve
        })
      }
      return Promise.resolve()
    })

    const wrapper = mount(PapersView, {
      global: { stubs: actionTableStubs },
    })
    await flushPromises()

    await deleteButton(wrapper, 'paper-a').trigger('click')
    await flushPromises()

    const buttonA = deleteButton(wrapper, 'paper-a')
    const buttonB = deleteButton(wrapper, 'paper-b')
    expect(buttonA.attributes('aria-busy')).toBe('true')
    expect((buttonA.element as HTMLButtonElement).disabled).toBe(true)
    expect((buttonB.element as HTMLButtonElement).disabled).toBe(false)
    expect(buttonB.attributes('aria-busy')).toBe('false')
    expect(confirm).toHaveBeenCalledTimes(1)

    await buttonB.trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledTimes(2)
    expect(getPaperStatus).toHaveBeenCalledWith('paper-b')
    expect(deletePaper).toHaveBeenCalledWith('paper-b', { force: false })

    releaseA?.()
    await flushPromises()
  })

  it('503 VECTOR_STORE_UNAVAILABLE shows 系统保护提示 alert, not raw-code toast', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    deletePaper.mockRejectedValue(
      new ApiClientError({ code: 'VECTOR_STORE_UNAVAILABLE', message: 'VECTOR_STORE_UNAVAILABLE' }, 503),
    )

    const wrapper = mount(PapersView, {
      global: { stubs: actionTableStubs },
    })
    await flushPromises()

    await deleteButton(wrapper, 'paper-a').trigger('click')
    await flushPromises()

    expect(alert).toHaveBeenCalledWith(
      PAPER_DELETE_COPY.vectorStoreUnavailable,
      PAPER_DELETE_COPY.vectorStoreUnavailableTitle,
      expect.objectContaining({ type: 'warning' }),
    )
    expect(PAPER_DELETE_COPY.vectorStoreUnavailableTitle).toBe('系统保护提示')
    expect(PAPER_DELETE_COPY.vectorStoreUnavailable).not.toMatch(/Chroma/i)
    expect(errorToast).not.toHaveBeenCalled()
    expect(errorToast).not.toHaveBeenCalledWith(expect.stringContaining('VECTOR_STORE_UNAVAILABLE'))
  })
})
