import { onUnmounted, ref } from 'vue'

import * as papersApi from '@/api/papers'
import type { PaperStatusData } from '@/api/types'
import { isTerminalStatus } from '@/utils/paperStatus'

export function usePaperStatus(paperId: string, intervalMs = 2000) {
  const status = ref<PaperStatusData | null>(null)
  const polling = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function pollOnce() {
    const res = await papersApi.getPaperStatus(paperId)
    status.value = res.data
    if (isTerminalStatus(res.data.status)) {
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
