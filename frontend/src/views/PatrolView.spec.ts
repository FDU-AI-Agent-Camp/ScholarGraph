import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import type { DataResponse, PatrolReport } from '@/api/types'

const mockRunPatrol = vi.fn()

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

import PatrolView from '@/views/PatrolView.vue'

const patrolReport: DataResponse<PatrolReport> = {
  data: {
    mode: 'lens_clash',
    paper_ids: ['hss-001', 'hss-002'],
    generated_at: '2026-05-19T11:00:00Z',
    insights: [
      {
        insight_id: 'ins-001',
        title: '理论视角冲突',
        summary: '两篇论文理论框架存在潜在冲突。',
        paper_ids: ['hss-001', 'hss-002'],
        node_refs: [
          { paper_id: 'hss-001', node_id: 'n_lens_a', label: '消费社会' },
          { paper_id: 'hss-002', node_id: 'n_lens_b', label: 'public sphere' },
        ],
      },
    ],
  },
  meta: { request_id: 'req-patrol-view' },
}

const globalStubs = {
  'el-input': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-form': { template: '<form class="patrol-form"><slot /></form>' },
  'el-form-item': { template: '<div class="patrol-form-item"><slot /></div>' },
  'el-radio-group': true,
  'el-radio': true,
  'el-button': { template: '<button @click="$attrs.onClick?.()"><slot /></button>' },
  'el-alert': {
    props: ['title'],
    template: '<div class="patrol-alert" :data-title="title" />',
  },
  'el-descriptions': { template: '<div class="patrol-summary"><slot /></div>' },
  'el-descriptions-item': { template: '<div><slot /></div>' },
  InsightCard: {
    props: ['variant', 'title', 'insightId', 'summary'],
    template: '<div class="patrol-insight" :data-title="title"><slot /></div>',
  },
  'el-table': { template: '<div class="patrol-node-refs"><slot /></div>' },
  'el-table-column': true,
}

describe('PatrolView', () => {
  beforeEach(() => {
    mockRunPatrol.mockReset()
  })

  it('shows validation error when paper_ids count is not two', async () => {
    const wrapper = mount(PatrolView, {
      global: { stubs: globalStubs },
    })

    await wrapper.find('input').setValue('hss-001')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).not.toHaveBeenCalled()
    expect(wrapper.find('.patrol-alert').attributes('data-title')).toMatch(/恰好 2/)
  })

  it('calls runPatrol with mode and renders insight node_refs', async () => {
    mockRunPatrol.mockResolvedValue(patrolReport)

    const wrapper = mount(PatrolView, {
      global: { stubs: globalStubs },
    })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['hss-001', 'hss-002'], { mode: 'lens_clash' })
    expect(wrapper.find('.patrol-summary').exists()).toBe(true)
    expect(wrapper.find('.patrol-insight').attributes('data-title')).toBe('理论视角冲突')
    expect(wrapper.find('.patrol-node-refs').exists()).toBe(true)
  })

  it('maps GRAPH_NOT_READY ApiClientError with seed hint', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = mount(PatrolView, {
      global: { stubs: globalStubs },
    })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-alert').attributes('data-title')).toContain('--seed-demo-graphs')
  })

  it('maps PATROL_INSUFFICIENT_DATA ApiClientError with mode hint', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '巡检数据不足' }, 422),
    )

    const wrapper = mount(PatrolView, {
      global: { stubs: globalStubs },
    })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-alert').attributes('data-title')).toContain('切换巡检模式')
  })

  it('clears prior validation error after a successful patrol run', async () => {
    mockRunPatrol.mockResolvedValue(patrolReport)

    const wrapper = mount(PatrolView, {
      global: { stubs: globalStubs },
    })

    await wrapper.find('input').setValue('hss-001')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.patrol-alert').attributes('data-title')).toMatch(/恰好 2/)

    await wrapper.find('input').setValue('hss-001,hss-002')
    mockRunPatrol.mockClear()
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['hss-001', 'hss-002'], { mode: 'lens_clash' })
    expect(wrapper.find('.patrol-summary').exists()).toBe(true)
    const alerts = wrapper.findAll('.patrol-alert')
    expect(alerts.some((node) => node.attributes('data-title')?.match(/恰好 2/))).toBe(false)
  })
})
