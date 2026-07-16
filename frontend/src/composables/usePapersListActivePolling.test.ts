import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { PaperSummary } from '@/api/types'
import {
  PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS,
  usePapersListActivePolling,
} from '@/composables/usePapersListActivePolling'

function mountPollingHarness(initial: PaperSummary[]) {
  const items = ref<PaperSummary[]>(initial)
  const refresh = vi.fn().mockResolvedValue(undefined)
  let api: ReturnType<typeof usePapersListActivePolling> | undefined

  const Host = defineComponent({
    setup() {
      api = usePapersListActivePolling(items, refresh)
      return () => h('div')
    },
  })

  const wrapper = mount(Host)
  return { wrapper, items, refresh, api: api! }
}

const processingRow: PaperSummary = {
  paper_id: 'p-active',
  title: 'Active',
  paradigm: 'HSS',
  status: 'processing',
  created_at: '2026-05-19T10:00:00Z',
}

const readyRow: PaperSummary = {
  paper_id: 'p-ready',
  title: 'Ready',
  paradigm: 'STEM',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
}

describe('usePapersListActivePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts interval when list has pending/processing/indexing rows', async () => {
    const { refresh, api } = mountPollingHarness([processingRow])
    api.sync()
    await nextTick()

    expect(refresh).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('stops interval when all rows reach terminal status', async () => {
    const { items, refresh, api } = mountPollingHarness([processingRow])
    api.sync()
    await nextTick()

    items.value = [readyRow]
    await nextTick()

    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS * 2)
    expect(refresh).toHaveBeenCalledTimes(0)
  })

  it('clears timer on unmount', async () => {
    const { wrapper, refresh, api } = mountPollingHarness([processingRow])
    api.sync()
    await nextTick()
    wrapper.unmount()

    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS * 2)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('self-heals: 10 ready idle → one processing mounts timer → ready destroys timer', async () => {
    const tenReady: PaperSummary[] = Array.from({ length: 10 }, (_, index) => ({
      paper_id: `p-ready-${index}`,
      title: `Ready ${index}`,
      paradigm: index % 2 === 0 ? 'STEM' : 'HSS',
      status: 'ready',
      created_at: '2026-05-19T10:00:00Z',
    }))
    const { items, refresh } = mountPollingHarness(tenReady)
    await nextTick()

    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS * 2)
    expect(refresh).not.toHaveBeenCalled()

    items.value = tenReady.map((row, index) => (index === 4 ? { ...row, status: 'processing' as const } : row))
    await nextTick()

    expect(vi.getTimerCount()).toBeGreaterThan(0)
    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS)
    expect(refresh).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS)
    expect(refresh).toHaveBeenCalledTimes(2)

    items.value = tenReady.map((row) => ({ ...row, status: 'ready' as const }))
    await nextTick()

    expect(vi.getTimerCount()).toBe(0)
    refresh.mockClear()
    await vi.advanceTimersByTimeAsync(PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS * 2)
    expect(refresh).not.toHaveBeenCalled()
  })
})
