import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { ApiClientError } from '@/api/client'
import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'

const mockRunPatrol = vi.fn()
const mockPush = vi.fn()

const paperStoreState = reactive({
  items: [] as Array<{ paper_id: string; title: string; status: string; paradigm: string }>,
  fetchList: vi.fn().mockResolvedValue(undefined),
})

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

vi.mock('@/stores/paper', () => ({
  usePaperStore: () => paperStoreState,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link-stub" :data-to="JSON.stringify(to)"><slot /></a>',
  },
}))

import PatrolView from '@/views/PatrolView.vue'

const contradictionReport: DataResponse<PatrolReport> = {
  data: {
    mode: 'contradiction',
    paper_ids: ['hss-001', 'hss-002'],
    generated_at: '2026-05-19T12:00:00Z',
    insights: [
      {
        insight_id: 'ins-002',
        title: '核心论点矛盾',
        summary: '两篇论文论点不一致。',
        status: 'ready',
        paper_ids: ['hss-001', 'hss-002'],
        node_refs: [],
      },
    ],
  },
  meta: { request_id: 'req-patrol-contradiction' },
}

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
        status: 'ready',
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
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<input class="patrol-select-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-option': true,
  'el-button': {
    inheritAttrs: false,
    props: ['loading'],
    template:
      '<button type="button" class="patrol-run-stub" :data-loading="loading ? \'true\' : \'false\'" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-alert': {
    props: ['title', 'description'],
    template: '<div class="patrol-alert" :data-title="title" :data-desc="description ?? \'\'" />',
  },
  InsightCard: {
    props: ['variant', 'title', 'insightId', 'summary'],
    template: '<div class="patrol-insight" :data-title="title" :data-variant="variant"><slot /></div>',
  },
}

async function mountPatrolView() {
  const wrapper = mount(PatrolView, { global: { stubs: globalStubs } })
  await flushPromises()
  return wrapper
}

async function setPaperSelection(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, paperA: string, paperB: string) {
  const selects = wrapper.findAll('.patrol-select-stub')
  await selects[0]?.setValue(paperA)
  await selects[1]?.setValue(paperB)
  await flushPromises()
}

describe('PatrolView', () => {
  beforeEach(() => {
    mockRunPatrol.mockReset()
    mockPush.mockReset()
    paperStoreState.items = []
    paperStoreState.fetchList.mockClear()
  })

  it('renders baseline page header and subtitle (7.1)', async () => {
    const wrapper = await mountPatrolView()

    expect(wrapper.find('.patrol-view__title').text()).toBe(PATROL_BASELINE_COPY.pageTitle)
    expect(wrapper.find('.patrol-view__subtitle').text()).toBe(PATROL_BASELINE_COPY.subtitle)
  })

  it('shows validation error when paper selection is incomplete (7.2)', async () => {
    const wrapper = await mountPatrolView()

    await setPaperSelection(wrapper, 'hss-001', '')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).not.toHaveBeenCalled()
    expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe(PATROL_BASELINE_COPY.validationExactTwo)
  })

  it('shows duplicate paper id warning with specific copy (7.2)', async () => {
    const wrapper = await mountPatrolView()

    await setPaperSelection(wrapper, 'hss-001', 'hss-001')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).not.toHaveBeenCalled()
    expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe(
      PATROL_BASELINE_COPY.validationDuplicate('hss-001'),
    )
  })

  it('uses segmented control with primary active state (7.3)', async () => {
    const wrapper = await mountPatrolView()

    expect(wrapper.find('.patrol-mode-segment').exists()).toBe(true)
    expect(wrapper.find('.patrol-mode-segment__item--active').text()).toContain(PATROL_BASELINE_COPY.modeLensClashLabel)

    const contradictionTab = wrapper.findAll('.patrol-mode-segment__item')[1]
    await contradictionTab.trigger('click')

    expect(wrapper.find('.patrol-mode-segment__item--active').text()).toContain(
      PATROL_BASELINE_COPY.modeContradictionLabel,
    )
  })

  it('shows baseline run button label before loading (§1.4.4)', async () => {
    const wrapper = await mountPatrolView()

    expect(wrapper.find('.patrol-run-stub').text()).toBe(PATROL_BASELINE_COPY.runButton)
  })

  it('calls runPatrol and shows loading label on button (7.4)', async () => {
    mockRunPatrol.mockImplementation(() => new Promise(() => undefined))

    const wrapper = await mountPatrolView()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-run-stub').text()).toBe(PATROL_BASELINE_COPY.runButtonLoading)
    expect(wrapper.find('.patrol-run-stub').attributes('data-loading')).toBe('true')
    expect(mockRunPatrol).toHaveBeenCalledWith(['hss-001', 'hss-002'], { mode: 'lens_clash' })
  })

  it('renders node_refs as graph deep links (7.5)', async () => {
    mockRunPatrol.mockResolvedValue(patrolReport)

    const wrapper = await mountPatrolView()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const link = wrapper.find('.router-link-stub')
    expect(link.exists()).toBe(true)
    expect(link.attributes('data-to')).toContain(RouteName.PaperGraph)
    expect(link.attributes('data-to')).toContain('n_lens_a')
  })

  it('maps GRAPH_NOT_READY to baseline error title and papers CTA (7.6)', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = await mountPatrolView()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
    await wrapper.find('.patrol-view__error-cta').trigger('click')
    expect(mockPush).toHaveBeenCalledWith({ name: RouteName.Papers })
  })

  it('maps PATROL_INSUFFICIENT_DATA to baseline error title and reset CTA (7.6)', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '巡检数据不足' }, 422),
    )

    const wrapper = await mountPatrolView()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-alert')
    expect(alert.attributes('data-title')).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(alert.attributes('data-desc')).toBe(PATROL_BASELINE_COPY.insufficientDataDescription)

    await wrapper.find('.patrol-view__error-cta').trigger('click')
    const selects = wrapper.findAll('.patrol-select-stub')
    expect((selects[0]?.element as HTMLInputElement).value).toBe('')
    expect((selects[1]?.element as HTMLInputElement).value).toBe('')
  })

  it('passes lens_clash report mode variant to InsightCard', async () => {
    mockRunPatrol.mockResolvedValue(patrolReport)

    const wrapper = await mountPatrolView()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-insight').attributes('data-variant')).toBe('lens_clash')
  })

  it('passes contradiction report mode variant to InsightCard', async () => {
    mockRunPatrol.mockResolvedValue(contradictionReport)

    const wrapper = await mountPatrolView()
    const contradictionTab = wrapper.findAll('.patrol-mode-segment__item')[1]
    await contradictionTab.trigger('click')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-insight').attributes('data-variant')).toBe('contradiction')
  })

  it('shows baseline error CTA labels from §1.4.4 error table (7.6)', async () => {
    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'GRAPH_NOT_READY', message: '图谱未就绪' }, 409))

    const wrapper = await mountPatrolView()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__error-cta').text()).toBe(PATROL_BASELINE_COPY.graphNotReadyCta)

    mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'PATROL_INSUFFICIENT_DATA', message: '数据不足' }, 422))
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(wrapper.find('.patrol-view__error-cta').text()).toBe(PATROL_BASELINE_COPY.insufficientDataCta)
  })

  it('clears prior validation error after a successful patrol run', async () => {
    mockRunPatrol.mockResolvedValue(patrolReport)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'hss-001', '')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()
    expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe(PATROL_BASELINE_COPY.validationExactTwo)

    await setPaperSelection(wrapper, 'hss-001', 'hss-002')
    mockRunPatrol.mockClear()
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalledWith(['hss-001', 'hss-002'], { mode: 'lens_clash' })
    expect(wrapper.find('.patrol-insight').exists()).toBe(true)
    expect(
      wrapper
        .findAll('.patrol-alert')
        .some((node) => node.attributes('data-title') === PATROL_BASELINE_COPY.validationExactTwo),
    ).toBe(false)
  })

  describe('robustness (API failures)', () => {
    it('shows PATROL_FAILED message and resets loading state', async () => {
      mockRunPatrol.mockRejectedValue(new ApiClientError({ code: 'PATROL_FAILED', message: '巡检失败' }, 500))

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'hss-001', 'hss-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe('巡检失败')
      expect(wrapper.find('.patrol-run-stub').attributes('data-loading')).toBe('false')
    })

    it('shows generic network error and resets loading state', async () => {
      mockRunPatrol.mockRejectedValue(new Error('network down'))

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'hss-001', 'hss-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('.patrol-alert').attributes('data-title')).toBe('network down')
      expect(wrapper.find('.patrol-run-stub').attributes('data-loading')).toBe('false')
    })
  })
})
