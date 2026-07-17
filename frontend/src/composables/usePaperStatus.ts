/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { onUnmounted, ref, type Ref } from 'vue'

import * as papersApi from '@/api/papers'
import type { PaperStatusData } from '@/api/types'
import { isTerminalStatus } from '@/utils/paperStatus'

export interface UsePaperStatusReturn {
  status: Ref<PaperStatusData | null>
  polling: Ref<boolean>
  start: () => void
  stop: () => void
  pollOnce: () => Promise<void>
}

export function usePaperStatus(paperId: string, intervalMs = 2000): UsePaperStatusReturn {
  const status = ref<PaperStatusData | null>(null)
  const polling = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function pollOnce(): Promise<void> {
    try {
      const res = await papersApi.getPaperStatus(paperId)
      status.value = res.data
      if (isTerminalStatus(res.data.status)) {
        stop()
      }
    } catch {
      stop()
    }
  }

  function start(): void {
    if (polling.value) return
    polling.value = true
    void pollOnce()
    timer = setInterval(() => void pollOnce(), intervalMs)
  }

  function stop(): void {
    polling.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(stop)

  return { status, polling, start, stop, pollOnce }
}
