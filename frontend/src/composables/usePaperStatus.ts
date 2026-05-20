import { onUnmounted, ref } from 'vue'

import * as papersApi from '@/api/papers'
import type { PaperStatusData } from '@/api/types'

const TERMINAL = new Set(['ready', 'failed'])

export function usePaperStatus(paperId: string, intervalMs = 2000) {
  const status = ref<PaperStatusData | null>(null)
  const polling = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function pollOnce() {
    const res = await papersApi.getPaperStatus(paperId)
    status.value = res.data
    if (TERMINAL.has(res.data.status)) {
      stop()
    }
  }

  function start() {
    if (polling.value) return
    polling.value = true
    void pollOnce()
    timer = setInterval(() => void pollOnce(), intervalMs)
  }

  function stop() {
    polling.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(stop)

  return { status, polling, start, stop, pollOnce }
}
