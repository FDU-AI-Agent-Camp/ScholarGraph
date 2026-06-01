/**
 * V1 DoD A-05～A-08 — 前后端联调联试（Mock LLM + 红路径反馈）。
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import * as client from '@/api/client'
import { parseQaStreamEvent } from '@/api/qaStream'
import * as patrolApi from '@/api/patrol'
import { runPatrol } from '@/api/patrol'
import type { PaperStatusData, PatrolReport } from '@/api/types'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { resolvePatrolApiError } from '@/utils/patrolForm'
import { buildHighlightStateMap } from '@/utils/paperGraph'
import { isFailedStatus } from '@/utils/paperStatus'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import patrolLensClashFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'

const mockListPapers = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
}))

const patrolReport = patrolLensClashFixture.data as PatrolReport

const patrolStubs = {
  'el-select': true,
  'el-option': true,
  'el-input': true,
  'el-space': { template: '<div><slot /></div>' },
  'el-icon': true,
  'el-button': {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  RouterLink: true,
  InsightCard: {
    props: ['variant', 'insightId'],
    template: '<div class="patrol-insight-fe" :data-variant="variant" />',
  },
  'el-alert': {
    inheritAttrs: false,
    props: ['title', 'description'],
    template: '<div class="patrol-alert-fe" v-bind="$attrs" :data-title="title" :data-description="description" />',
  },
  BadgeParadigm: true,
}

async function mountPatrolRoute() {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/patrol')
  await router.isReady()
  const wrapper = mount(routerViewShell, {
    global: { plugins: [router], stubs: patrolStubs },
  })
  await flushPromises()
  return wrapper
}

describe('V1 DoD A-05～A-08 FE↔BE — SSE + patrol contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListPapers.mockResolvedValue({
      data: {
        items: [
          { paper_id: 'hss-001', title: 'A', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:00:00Z' },
          { paper_id: 'hss-002', title: 'B', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:10:00Z' },
        ],
        total: 2,
        offset: 0,
        limit: 20,
      },
      meta: { request_id: 'fe-be' },
    })
  })

  describe('A-05 SSE QA (mock LLM frames)', () => {
    it('parses backend mock SSE frames including disclaimer text', () => {
      const frames = [
        { event: 'message', data: { delta: '根据知识图谱' } },
        { event: 'citation', data: { paper_id: 'hss-001', node_id: 'n1', label: '核心论点' } },
        { event: 'message', data: { delta: '（Mock 答复：LLM 云服务尚未接入，仅供联调与演示。）' } },
        { event: 'done', data: { answer_id: 'ans-hss-001' } },
      ]
      const parsed = frames.map((f) => parseQaStreamEvent(f.event, JSON.stringify(f.data)))
      expect(parsed.every((item) => item !== null)).toBe(true)
      const messages = parsed
        .filter((item) => item?.type === 'message')
        .map((item) => (item?.type === 'message' ? item.data.delta : ''))
        .join('')
      expect(messages).toContain('尚未接入')
    })

    it('parses SSE error event for GRAPH_NOT_FOUND feedback path', () => {
      const parsed = parseQaStreamEvent(
        'error',
        JSON.stringify({ code: 'GRAPH_NOT_FOUND', message: '论文 hss-001 的图谱尚未建好' }),
      )
      expect(parsed?.type).toBe('error')
      if (parsed?.type === 'error') {
        expect(parsed.data.code).toBe('GRAPH_NOT_FOUND')
        expect(parsed.data.message).toContain('图谱尚未建好')
      }
    })

    it('chains mock citation frame into graph highlight map (BE mock SSE parity)', () => {
      const citation = parseQaStreamEvent(
        'citation',
        JSON.stringify({ paper_id: 'hss-001', node_id: 'n1', label: '核心论点' }),
      )
      expect(citation?.type).toBe('citation')
      if (citation?.type !== 'citation') {
        return
      }
      const nodeIds = graphFixture.data.nodes.map((node) => node.id)
      const states = buildHighlightStateMap(nodeIds, citation.data.node_id)
      expect(states.n1).toBe('active')
    })

    it('ignores malformed SSE JSON without crashing parser', () => {
      expect(parseQaStreamEvent('message', '{not-json')).toBeNull()
      expect(parseQaStreamEvent('unknown_event', '{}')).toBeNull()
    })
  })

  describe('A-06 patrol mode + red paths', () => {
    it('runPatrol client forwards contradiction mode to POST /patrol', async () => {
      const postSpy = vi.spyOn(client, 'postData').mockResolvedValue({
        data: {
          mode: 'contradiction',
          paper_ids: ['hss-001', 'hss-002'],
          insights: [],
          generated_at: '2026-05-19T12:00:00Z',
        },
        meta: { request_id: 'req' },
      })

      const result = await runPatrol(['hss-001', 'hss-002'], { mode: 'contradiction' })
      expect(postSpy).toHaveBeenCalledWith('/patrol', {
        paper_ids: ['hss-001', 'hss-002'],
        mode: 'contradiction',
      })
      expect(result.data.mode).toBe('contradiction')
      postSpy.mockRestore()
    })

    it('PatrolView shows baseline copy on 409 GRAPH_NOT_READY', async () => {
      vi.spyOn(patrolApi, 'runPatrol').mockRejectedValue(
        new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409),
      )

      const wrapper = await mountPatrolRoute()
      await wrapper.find('.patrol-view__run').trigger('click')
      await flushPromises()

      const alert = wrapper.find('.patrol-view__error-panel .patrol-alert-fe')
      expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
    })

    it('PatrolView shows insufficient-data copy on 422', async () => {
      vi.spyOn(patrolApi, 'runPatrol').mockRejectedValue(
        new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '数据不足' }, 422),
      )

      const wrapper = await mountPatrolRoute()
      await wrapper.find('.patrol-view__run').trigger('click')
      await flushPromises()

      const alert = wrapper.find('.patrol-view__error-panel .patrol-alert-fe')
      expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
      expect(alert.attributes('data-description')).toBe(PATROL_BASELINE_COPY.insufficientDataDescription)
    })

    it('maps unknown patrol error code to generic presentation', () => {
      const presentation = resolvePatrolApiError('SERVER', '服务异常')
      expect(presentation.title).toBe('服务异常')
    })

    it('successful patrol renders insight variant from fixture', async () => {
      vi.spyOn(patrolApi, 'runPatrol').mockResolvedValue({ data: patrolReport, meta: { request_id: 'ok' } })

      const wrapper = await mountPatrolRoute()
      await wrapper.find('.patrol-view__run').trigger('click')
      await flushPromises()

      expect(wrapper.find('.patrol-insight-fe').attributes('data-variant')).toBe('lens_clash')
      expect(patrolReport.insights[0]?.node_refs.length).toBeGreaterThan(0)
    })
  })

  describe('A-07 / A-08 pipeline red feedback (FE status contract)', () => {
    it('failed status fixture exposes LLM_JSON_INVALID during classifying (M0/M1 blocked)', () => {
      const data = failedStatusFixture.data as PaperStatusData
      expect(isFailedStatus(data)).toBe(true)
      expect(data.error_code).toBe('LLM_JSON_INVALID')
      expect(data.failed_during).toBe('classifying')
      expect(data.message).toBeTruthy()
    })

    it('detail not-ready copy blocks QA until paper is ready', () => {
      expect(DETAIL_BASELINE_COPY.notReadyAlert).toContain('尚未 ready')
    })
  })
})

describe('V1 DoD A-05～A-08 route smoke', () => {
  it('patrol route name matches collaboration §3', async () => {
    setActivePinia(createPinia())
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/patrol')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe(RouteName.Patrol)
  })
})
