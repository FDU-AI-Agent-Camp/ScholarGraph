import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as papersApi from '@/api/papers'
import type { PaperDetail, PaperSummary, UnifiedPaperGraph } from '@/api/types'

export const usePaperStore = defineStore('paper', () => {
  const items = ref<PaperSummary[]>([])
  const total = ref(0)
  const loading = ref(false)
  const currentPaper = ref<PaperDetail | null>(null)
  const currentGraph = ref<UnifiedPaperGraph | null>(null)

  async function fetchList(params?: Parameters<typeof papersApi.listPapers>[0]) {
    loading.value = true
    try {
      const res = await papersApi.listPapers(params)
      items.value = res.data.items
      total.value = res.data.total
    } finally {
      loading.value = false
    }
  }

  async function fetchDetail(paperId: string) {
    loading.value = true
    try {
      const res = await papersApi.getPaper(paperId)
      currentPaper.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchGraph(paperId: string) {
    const res = await papersApi.getPaperGraph(paperId)
    currentGraph.value = res.data
    return res.data
  }

  function clearCurrent() {
    currentPaper.value = null
    currentGraph.value = null
  }

  return {
    items,
    total,
    loading,
    currentPaper,
    currentGraph,
    fetchList,
    fetchDetail,
    fetchGraph,
    clearCurrent,
  }
})
