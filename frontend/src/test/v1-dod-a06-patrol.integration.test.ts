/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD A-06 — 双文巡检：mode + node_refs + 409/422 错误映射。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import patrolLensClashFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'
import type { PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import { mountAppRoute } from '@/test/helpers/mountRoute'
import { resolvePatrolApiError } from '@/utils/patrolForm'

const mockListPapers = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
}))

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

const patrolReport = patrolLensClashFixture.data as PatrolReport

const routeStubs = {
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<select class="patrol-select-dod" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  'el-option': true,
  'el-input': true,
  'el-space': { template: '<div><slot /></div>' },
  'el-icon': true,
  'el-button': {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-dod" :href="String(to)"><slot /></a>',
  },
  InsightCard: {
    props: ['variant', 'insightId', 'title'],
    template: '<div class="patrol-insight-dod" :data-variant="variant" :data-id="insightId" />',
  },
  'el-alert': {
    inheritAttrs: false,
    props: ['title', 'description'],
    template:
      '<div class="patrol-alert-dod" v-bind="$attrs" :data-title="title" :data-description="description"><slot /></div>',
  },
  BadgeParadigm: true,
}

async function mountPatrol() {
  setActivePinia(createPinia())
  return mountAppRoute('/patrol', routeStubs)
}

describe('V1 DoD A-06 — patrol mode, node_refs, and error mapping', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListPapers.mockResolvedValue({
      data: {
        items: [
          {
            paper_id: 'hss-001',
            title: 'A',
            paradigm: 'HSS',
            status: 'ready',
            created_at: '2026-05-19T10:00:00Z',
          },
          {
            paper_id: 'hss-002',
            title: 'B',
            paradigm: 'HSS',
            status: 'ready',
            created_at: '2026-05-19T10:10:00Z',
          },
        ],
        total: 2,
        offset: 0,
        limit: 20,
      },
      meta: { request_id: 'dod-patrol-list' },
    })
  })

  it('mounts /patrol and loads paper options for dual selection', async () => {
    const { wrapper, router } = await mountPatrol()
    expect(router.currentRoute.value.name).toBe(RouteName.Patrol)
    expect(wrapper.find('.patrol-view__title').text()).toBe(PATROL_BASELINE_COPY.pageTitle)
    expect(mockListPapers).toHaveBeenCalled()
  })

  it('runPatrol sends mode lens_clash and renders insight with node_refs', async () => {
    mockRunPatrol.mockResolvedValue({ data: patrolReport, meta: { request_id: 'dod-patrol' } })

    const { wrapper } = await mountPatrol()
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(
      expect.arrayContaining(['hss-001', 'hss-002']),
      expect.objectContaining({ mode: 'lens_clash' }),
    )
    expect(wrapper.find('.patrol-insight-dod').attributes('data-variant')).toBe('lens_clash')
    expect(patrolReport.insights[0]?.node_refs.length).toBeGreaterThan(0)
  })

  it('maps GRAPH_NOT_READY to baseline title and papers CTA', () => {
    const presentation = resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪')
    expect(presentation.title).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
    expect(presentation.ctaLabel).toBe(PATROL_BASELINE_COPY.graphNotReadyCta)
    expect(presentation.ctaKind).toBe('papers')
  })

  it('maps PATROL_INSUFFICIENT_DATA to baseline copy and reset action', () => {
    const presentation = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
    expect(presentation.title).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(presentation.ctaLabel).toBe(PATROL_BASELINE_COPY.insufficientDataCta)
    expect(presentation.ctaKind).toBe('reset-selection')
  })

  it('surfaces GRAPH_NOT_READY inline after runPatrol 409', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const { wrapper } = await mountPatrol()
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-view__error-panel .patrol-alert-dod')
    expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
  })

  it('surfaces PATROL_INSUFFICIENT_DATA inline after runPatrol 422', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '巡检数据不足' }, 422),
    )

    const { wrapper } = await mountPatrol()
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-view__error-panel .patrol-alert-dod')
    expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(alert.attributes('data-description')).toBe(PATROL_BASELINE_COPY.insufficientDataDescription)
  })
})
