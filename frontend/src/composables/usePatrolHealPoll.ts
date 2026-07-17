/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Exponential backoff heal polling when Patrol returned INDEX_NOT_READY.
 * Quietly re-runs patrol until is_degraded clears or attempts are exhausted.
 */
import { onUnmounted, ref, type Ref } from 'vue'

import type { PatrolMode, PatrolReport } from '@/api/types'
import { PATROL_HEAL_POLL_DELAYS_MS, shouldHealPoll, extractReportDegradation } from '@/utils/patrolDegradation'

export interface UsePatrolHealPollOptions {
  report: Ref<PatrolReport | null>
  paperIds: Ref<[string, string] | null>
  mode: Ref<PatrolMode>
  runPatrol: (paperIds: string[], mode: PatrolMode) => Promise<PatrolReport>
  delaysMs?: readonly number[]
}

export function usePatrolHealPoll(options: UsePatrolHealPollOptions) {
  const healing = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let generation = 0

  function clearHealTimer(): void {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function stopHealPoll(): void {
    generation += 1
    clearHealTimer()
    healing.value = false
  }

  function scheduleHealPoll(): void {
    stopHealPoll()
    const report = options.report.value
    if (!report) {
      return
    }
    const profile = extractReportDegradation(report)
    if (!shouldHealPoll(profile)) {
      return
    }
    const paperIds = options.paperIds.value
    if (!paperIds) {
      return
    }

    const delays = options.delaysMs ?? PATROL_HEAL_POLL_DELAYS_MS
    const myGeneration = generation
    healing.value = true

    const runAttempt = async (attemptIndex: number): Promise<void> => {
      if (myGeneration !== generation) {
        return
      }
      if (attemptIndex >= delays.length) {
        healing.value = false
        return
      }
      timer = setTimeout(async () => {
        if (myGeneration !== generation) {
          return
        }
        try {
          const next = await options.runPatrol([...paperIds], options.mode.value)
          if (myGeneration !== generation) {
            return
          }
          options.report.value = next
          const nextProfile = extractReportDegradation(next)
          if (!shouldHealPoll(nextProfile)) {
            healing.value = false
            return
          }
          await runAttempt(attemptIndex + 1)
        } catch {
          if (myGeneration === generation) {
            await runAttempt(attemptIndex + 1)
          }
        }
      }, delays[attemptIndex])
    }

    void runAttempt(0)
  }

  onUnmounted(() => {
    stopHealPoll()
  })

  return {
    healing,
    scheduleHealPoll,
    stopHealPoll,
  }
}
