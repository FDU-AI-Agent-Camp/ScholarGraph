/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { onUnmounted, watch, type Ref } from 'vue'

import type { PaperSummary } from '@/api/types'
import { listHasActivePollStatus } from '@/utils/paperStatus'

/** Low-frequency list refresh while any row is non-terminal (pending / processing / indexing). */
export const PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS = 8_000

export interface UsePapersListActivePollingOptions {
  intervalMs?: number
}

/**
 * Smart active-only polling for ``/papers``: one timer, ``fetchList`` refresh, auto stop when idle.
 */
export function usePapersListActivePolling(
  items: Ref<PaperSummary[]>,
  refresh: () => Promise<void>,
  options?: UsePapersListActivePollingOptions,
): { sync: () => void; stop: () => void } {
  const intervalMs = options?.intervalMs ?? PAPERS_LIST_ACTIVE_POLL_INTERVAL_MS
  let timer: ReturnType<typeof setInterval> | null = null

  function stop(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function sync(): void {
    if (listHasActivePollStatus(items.value)) {
      if (timer === null) {
        timer = setInterval(() => {
          void refresh().catch(() => undefined)
        }, intervalMs)
      }
      return
    }
    stop()
  }

  watch(items, sync, { deep: true })
  onUnmounted(stop)
  sync()

  return { sync, stop }
}
