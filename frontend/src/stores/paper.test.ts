/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { PaperDetail, PaperSummary, UnifiedPaperGraph } from '@/api/types'

const mockListPapers = vi.fn()
const mockGetPaper = vi.fn()
const mockGetPaperGraph = vi.fn()

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: (...args: unknown[]) => mockGetPaper(...args),
  getPaperGraph: (...args: unknown[]) => mockGetPaperGraph(...args),
}))

import { usePaperStore } from '@/stores/paper'

const sampleSummary: PaperSummary = {
  paper_id: 'hss-001',
  title: '样例',
  paradigm: 'HSS',
  status: 'ready',
  created_at: '2026-05-19T10:00:00Z',
}

const sampleDetail: PaperDetail = {
  ...sampleSummary,
  classification: undefined,
}

const sampleGraph: UnifiedPaperGraph = {
  paper_id: 'hss-001',
  paradigm: 'HSS',
  nodes: [],
  edges: [],
}

describe('usePaperStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockListPapers.mockReset()
    mockGetPaper.mockReset()
    mockGetPaperGraph.mockReset()
  })

  it('fetchList assigns PaperSummary items', async () => {
    mockListPapers.mockResolvedValue({
      data: { items: [sampleSummary], total: 1, offset: 0, limit: 20 },
      meta: { request_id: 'r1' },
    })
    const store = usePaperStore()

    await store.fetchList({ status: 'ready' })

    expect(store.items).toHaveLength(1)
    expect(store.items[0]?.paper_id).toBe('hss-001')
    expect(store.lastError).toBeNull()
  })

  it('fetchList records ApiClientError message in lastError', async () => {
    mockListPapers.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))
    const store = usePaperStore()

    await expect(store.fetchList()).rejects.toBeInstanceOf(ApiClientError)
    expect(store.lastError).toBe('服务不可用')
  })

  it('fetchList records generic Error via getUnknownErrorMessage', async () => {
    mockListPapers.mockRejectedValue(new Error('network down'))
    const store = usePaperStore()

    await expect(store.fetchList()).rejects.toThrow('network down')
    expect(store.lastError).toBe('network down')
  })

  it('fetchDetail sets currentPaper', async () => {
    mockGetPaper.mockResolvedValue({
      data: sampleDetail,
      meta: { request_id: 'r2' },
    })
    const store = usePaperStore()

    await store.fetchDetail('hss-001')

    expect(store.currentPaper?.paper_id).toBe('hss-001')
    expect(store.loading).toBe(false)
  })

  it('fetchDetail records ApiClientError in lastError and clears loading', async () => {
    mockGetPaper.mockRejectedValue(new ApiClientError({ code: 'NOT_FOUND', message: '论文不存在' }, 404))
    const store = usePaperStore()

    await expect(store.fetchDetail('missing')).rejects.toBeInstanceOf(ApiClientError)
    expect(store.lastError).toBe('论文不存在')
    expect(store.currentPaper).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('fetchDetail records generic Error via getUnknownErrorMessage', async () => {
    mockGetPaper.mockRejectedValue(new Error('network down'))
    const store = usePaperStore()

    await expect(store.fetchDetail('hss-001')).rejects.toThrow('network down')
    expect(store.lastError).toBe('network down')
    expect(store.loading).toBe(false)
  })

  it('fetchGraph returns UnifiedPaperGraph and caches currentGraph', async () => {
    mockGetPaperGraph.mockResolvedValue({
      data: sampleGraph,
      meta: { request_id: 'r3' },
    })
    const store = usePaperStore()

    const graph = await store.fetchGraph('hss-001')

    expect(graph.nodes).toEqual([])
    expect(store.currentGraph?.paper_id).toBe('hss-001')
  })

  it('fetchGraph records ApiClientError in lastError without clearing prior graph', async () => {
    mockGetPaperGraph.mockResolvedValueOnce({
      data: sampleGraph,
      meta: { request_id: 'r3' },
    })
    mockGetPaperGraph.mockRejectedValueOnce(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))
    const store = usePaperStore()
    await store.fetchGraph('hss-001')

    await expect(store.fetchGraph('hss-001')).rejects.toBeInstanceOf(ApiClientError)
    expect(store.lastError).toBe('图谱未就绪')
    expect(store.currentGraph?.paper_id).toBe('hss-001')
  })

  it('fetchGraph records generic Error via getUnknownErrorMessage', async () => {
    mockGetPaperGraph.mockRejectedValue(new Error('network timeout'))
    const store = usePaperStore()

    await expect(store.fetchGraph('hss-001')).rejects.toThrow('network timeout')
    expect(store.lastError).toBe('network timeout')
    expect(store.currentGraph).toBeNull()
  })

  it('clearCurrent resets detail and graph refs', async () => {
    mockGetPaper.mockResolvedValue({ data: sampleDetail, meta: { request_id: 'r4' } })
    mockGetPaperGraph.mockResolvedValue({ data: sampleGraph, meta: { request_id: 'r5' } })
    const store = usePaperStore()
    await store.fetchDetail('hss-001')
    await store.fetchGraph('hss-001')

    store.clearCurrent()

    expect(store.currentPaper).toBeNull()
    expect(store.currentGraph).toBeNull()
  })
})
