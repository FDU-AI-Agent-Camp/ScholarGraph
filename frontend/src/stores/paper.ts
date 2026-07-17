/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { defineStore } from 'pinia'
import { ref, type Ref } from 'vue'

import * as papersApi from '@/api/papers'
import type { PaperDetail, PaperStatus, PaperSummary, Paradigm, UnifiedPaperGraph } from '@/api/types'
import { getUnknownErrorMessage, logUnknownError } from '@/utils/errors'

export interface PaperListQuery {
  paradigm?: Paradigm
  status?: PaperStatus
  offset?: number
  limit?: number
}

export interface FetchListOptions {
  silent?: boolean
}

export interface PaperStoreState {
  items: Ref<PaperSummary[]>
  total: Ref<number>
  loading: Ref<boolean>
  lastError: Ref<string | null>
  currentPaper: Ref<PaperDetail | null>
  currentGraph: Ref<UnifiedPaperGraph | null>
}

export const usePaperStore = defineStore(
  'paper',
  (): PaperStoreState & {
    fetchList: (params?: PaperListQuery, options?: FetchListOptions) => Promise<void>
    fetchDetail: (paperId: string) => Promise<void>
    fetchGraph: (paperId: string) => Promise<UnifiedPaperGraph>
    clearCurrent: () => void
  } => {
    const items = ref<PaperSummary[]>([])
    const total = ref(0)
    const loading = ref(false)
    const lastError = ref<string | null>(null)
    const currentPaper = ref<PaperDetail | null>(null)
    const currentGraph = ref<UnifiedPaperGraph | null>(null)

    async function fetchList(params?: PaperListQuery, options?: FetchListOptions): Promise<void> {
      const silent = options?.silent === true
      if (!silent) {
        loading.value = true
      }
      lastError.value = null
      try {
        const res = await papersApi.listPapers(params)
        items.value = res.data.items
        total.value = res.data.total
      } catch (error: unknown) {
        logUnknownError('paper.fetchList', error)
        lastError.value = getUnknownErrorMessage(error)
        throw error
      } finally {
        if (!silent) {
          loading.value = false
        }
      }
    }

    async function fetchDetail(paperId: string): Promise<void> {
      loading.value = true
      lastError.value = null
      try {
        const res = await papersApi.getPaper(paperId)
        currentPaper.value = res.data
      } catch (error: unknown) {
        logUnknownError('paper.fetchDetail', error)
        lastError.value = getUnknownErrorMessage(error)
        throw error
      } finally {
        loading.value = false
      }
    }

    async function fetchGraph(paperId: string): Promise<UnifiedPaperGraph> {
      lastError.value = null
      try {
        const res = await papersApi.getPaperGraph(paperId)
        currentGraph.value = res.data
        return res.data
      } catch (error: unknown) {
        logUnknownError('paper.fetchGraph', error)
        lastError.value = getUnknownErrorMessage(error)
        throw error
      }
    }

    function clearCurrent(): void {
      currentPaper.value = null
      currentGraph.value = null
    }

    return {
      items,
      total,
      loading,
      lastError,
      currentPaper,
      currentGraph,
      fetchList,
      fetchDetail,
      fetchGraph,
      clearCurrent,
    }
  },
)
