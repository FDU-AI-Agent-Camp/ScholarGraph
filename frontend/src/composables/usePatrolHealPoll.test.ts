/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'

import type { PatrolMode, PatrolReport } from '@/api/types'
import { usePatrolHealPoll, type UsePatrolHealPollOptions } from '@/composables/usePatrolHealPoll'

function degradedReport(): PatrolReport {
  return {
    mode: 'method_overlap',
    paper_ids: ['stem-001', 'stem-002'],
    generated_at: '2026-07-13T19:15:00Z',
    insights: [
      {
        insight_id: 'ins-1',
        title: '方法重叠',
        summary: '图谱比对完成。',
        status: 'ready',
        paper_ids: ['stem-001', 'stem-002'],
        node_refs: [],
        is_degraded: true,
        degradation_profile: {
          component: 'RAG_CONTEXT',
          reason_code: 'INDEX_NOT_READY',
          affected_papers: ['stem-001'],
          severity: 'WARNING',
          timestamp: '2026-07-13T19:15:00Z',
        },
      },
    ],
  }
}

function healthyReport(): PatrolReport {
  return {
    mode: 'method_overlap',
    paper_ids: ['stem-001', 'stem-002'],
    generated_at: '2026-07-13T19:16:00Z',
    insights: [
      {
        insight_id: 'ins-1',
        title: '方法重叠',
        summary: '图谱比对完成，含原文证据。',
        status: 'ready',
        paper_ids: ['stem-001', 'stem-002'],
        node_refs: [],
        is_degraded: false,
        degradation_profile: null,
      },
    ],
  }
}

function mountHealPoll(options: UsePatrolHealPollOptions) {
  let api: ReturnType<typeof usePatrolHealPoll> | undefined
  const Host = defineComponent({
    setup() {
      api = usePatrolHealPoll(options)
      return () => null
    },
  })
  const wrapper = mount(Host)
  if (api === undefined) {
    throw new Error('usePatrolHealPoll did not initialize')
  }
  return { wrapper, api }
}

describe('usePatrolHealPoll', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('schedules backoff poll and clears banner state when index becomes ready', async () => {
    const report = ref<PatrolReport | null>(degradedReport())
    const paperIds = ref<[string, string] | null>(['stem-001', 'stem-002'])
    const mode = ref<PatrolMode>('method_overlap')
    const runPatrol = vi.fn().mockResolvedValue(healthyReport())

    const { wrapper, api } = mountHealPoll({
      report,
      paperIds,
      mode,
      runPatrol,
      delaysMs: [10_000, 30_000],
    })

    api.scheduleHealPoll()
    expect(api.healing.value).toBe(true)

    await vi.advanceTimersByTimeAsync(10_000)
    await nextTick()

    expect(runPatrol).toHaveBeenCalledTimes(1)
    expect(report.value?.insights[0]?.is_degraded).toBe(false)
    expect(api.healing.value).toBe(false)

    // Further ticks should not storm the network
    await vi.advanceTimersByTimeAsync(60_000)
    expect(runPatrol).toHaveBeenCalledTimes(1)

    api.stopHealPoll()
    wrapper.unmount()
  })

  it('does not schedule when reason is not INDEX_NOT_READY', () => {
    const report = ref<PatrolReport | null>({
      ...degradedReport(),
      insights: [
        {
          ...degradedReport().insights[0]!,
          degradation_profile: {
            component: 'RAG_CONTEXT',
            reason_code: 'QUERY_FAILED',
            affected_papers: ['stem-001'],
            severity: 'WARNING',
            timestamp: '2026-07-13T19:15:00Z',
          },
        },
      ],
    })
    const paperIds = ref<[string, string] | null>(['stem-001', 'stem-002'])
    const mode = ref<PatrolMode>('method_overlap')
    const runPatrol = vi.fn()

    const { wrapper, api } = mountHealPoll({
      report,
      paperIds,
      mode,
      runPatrol,
      delaysMs: [1_000],
    })

    api.scheduleHealPoll()
    expect(api.healing.value).toBe(false)
    expect(runPatrol).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
