import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { ApiClientError } from '@/api/client'
import type { DataResponse, PatrolMode, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import { patrolBaselineCopyV2 } from '@/test/helpers/patrolV2Copy'
import { PATROL_MODE_OPTIONS } from '@/utils/patrolViewHelpers'
import patrolMethodOverlapFixture from '../../../docs/api/fixtures/patrol-method-overlap.json'

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
        is_degraded: false,
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
        is_degraded: false,
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
      '<button type="button" class="patrol-run-stub" :data-loading="loading ? \'true\' : \'false\'" v-bind="$attrs"><slot /></button>',
  },
  'el-alert': {
    props: ['title', 'description'],
    template: '<div class="patrol-alert" :data-title="title" :data-desc="description ?? \'\'" />',
  },
  // Slot must pass through so F10 structured_points assertions see production children.
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

async function selectModeByLabel(wrapper: Awaited<ReturnType<typeof mountPatrolView>>, label: string) {
  const tab = wrapper.findAll('.patrol-mode-segment__item').find((node) => node.text().includes(label))
  expect(tab, `missing mode tab for label: ${label}`).toBeTruthy()
  await tab!.trigger('click')
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

  it('shows RAG degradation banner when is_degraded (P9/F8)', async () => {
    mockRunPatrol.mockResolvedValue({
      data: {
        mode: 'method_overlap',
        paper_ids: ['stem-001', 'stem-002'],
        generated_at: '2026-07-13T19:15:00Z',
        insights: [
          {
            insight_id: 'ins-mo-1',
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
      },
      meta: { request_id: 'req-degraded' },
    })

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'stem-001', 'stem-002')
    // switch mode isn't required — report content drives the banner
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const banner = wrapper.find('.patrol-view__degradation-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.attributes('data-title')).toBe(PATROL_BASELINE_COPY.degradationBannerTitle)
    expect(banner.attributes('data-desc')).toContain('stem-001')
    expect(wrapper.text()).toContain(PATROL_BASELINE_COPY.degradationEvidencePlaceholder)
  })

  describe('FE-H1 heal wiring (FakeTimers)', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('schedules heal poll after INDEX_NOT_READY and clears banner when index heals', async () => {
      const degradedEnvelope: DataResponse<PatrolReport> = {
        data: {
          mode: 'method_overlap',
          paper_ids: ['stem-001', 'stem-002'],
          generated_at: '2026-07-13T19:15:00Z',
          insights: [
            {
              insight_id: 'ins-mo-heal',
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
        },
        meta: { request_id: 'req-degraded-heal-1' },
      }

      const healthyEnvelope: DataResponse<PatrolReport> = {
        data: {
          mode: 'method_overlap',
          paper_ids: ['stem-001', 'stem-002'],
          generated_at: '2026-07-13T19:16:00Z',
          insights: [
            {
              insight_id: 'ins-mo-heal',
              title: '方法重叠',
              summary: '图谱比对完成，含原文证据。',
              status: 'ready',
              paper_ids: ['stem-001', 'stem-002'],
              node_refs: [{ paper_id: 'stem-001', node_id: 'n_method', label: 'ResNet-Light' }],
              is_degraded: false,
              degradation_profile: null,
            },
          ],
        },
        meta: { request_id: 'req-degraded-heal-2' },
      }

      mockRunPatrol.mockResolvedValueOnce(degradedEnvelope).mockResolvedValueOnce(healthyEnvelope)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(mockRunPatrol).toHaveBeenCalledTimes(1)
      expect(wrapper.find('.patrol-view__degradation-banner').exists()).toBe(true)
      expect(wrapper.find('.patrol-view__healing-hint').exists()).toBe(true)
      expect(wrapper.find('.patrol-view__healing-hint').text()).toBe(PATROL_BASELINE_COPY.degradationHealingHint)
      expect(wrapper.text()).toContain(PATROL_BASELINE_COPY.degradationEvidencePlaceholder)

      await vi.advanceTimersByTimeAsync(10_000)
      await flushPromises()

      // Ultimate guard: View fed scheduleHealPoll → composable re-ran patrol.
      expect(mockRunPatrol).toHaveBeenCalledTimes(2)
      expect(wrapper.find('.patrol-view__degradation-banner').exists()).toBe(false)
      expect(wrapper.find('.patrol-view__healing-hint').exists()).toBe(false)
      expect(wrapper.text()).not.toContain(PATROL_BASELINE_COPY.degradationEvidencePlaceholder)
      expect(wrapper.text()).toContain('ResNet-Light')

      await vi.advanceTimersByTimeAsync(60_000)
      await flushPromises()
      expect(mockRunPatrol).toHaveBeenCalledTimes(2)

      wrapper.unmount()
    })

    it('half-contract is_degraded without profile still banners and heals', async () => {
      mockRunPatrol
        .mockResolvedValueOnce({
          data: {
            mode: 'method_overlap',
            paper_ids: ['stem-001', 'stem-002'],
            generated_at: '2026-07-13T19:15:00Z',
            insights: [
              {
                insight_id: 'ins-half',
                title: '方法重叠',
                summary: '图谱比对完成。',
                status: 'ready',
                paper_ids: ['stem-001', 'stem-002'],
                node_refs: [],
                is_degraded: true,
              },
            ],
          },
          meta: { request_id: 'req-half-1' },
        } satisfies DataResponse<PatrolReport>)
        .mockResolvedValueOnce({
          data: {
            mode: 'method_overlap',
            paper_ids: ['stem-001', 'stem-002'],
            generated_at: '2026-07-13T19:16:00Z',
            insights: [
              {
                insight_id: 'ins-half',
                title: '方法重叠',
                summary: '已补齐证据。',
                status: 'ready',
                paper_ids: ['stem-001', 'stem-002'],
                node_refs: [],
                is_degraded: false,
              },
            ],
          },
          meta: { request_id: 'req-half-2' },
        } satisfies DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      expect(wrapper.find('.patrol-view__degradation-banner').exists()).toBe(true)
      expect(wrapper.find('.patrol-view__healing-hint').exists()).toBe(true)
      expect(wrapper.text()).toContain(PATROL_BASELINE_COPY.degradationEvidencePlaceholder)

      await vi.advanceTimersByTimeAsync(10_000)
      await flushPromises()

      expect(mockRunPatrol).toHaveBeenCalledTimes(2)
      expect(wrapper.find('.patrol-view__degradation-banner').exists()).toBe(false)
      expect(wrapper.find('.patrol-view__healing-hint').exists()).toBe(false)

      wrapper.unmount()
    })
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

  it('renders channel-B insufficient_data insights with warning card (F7)', async () => {
    mockRunPatrol.mockResolvedValue({
      data: {
        mode: 'method_overlap',
        paper_ids: ['hss-001', 'hss-002'],
        generated_at: '2026-07-14T02:00:00Z',
        insights: [
          {
            insight_id: 'ins-method-overlap-001',
            title: '方法重叠（Method Overlap）',
            summary: 'HSS 范式不支持 method_overlap',
            status: 'insufficient_data',
            paper_ids: ['hss-001', 'hss-002'],
            node_refs: [{ paper_id: 'hss-001', node_id: 'n1', label: 'should-hide-link' }],
            exclusion_logic: {
              phase: 'PARADIGM_GATE',
              reason_code: 'PARADIGM_UNSUPPORTED',
              description: '当前文献属于 HSS 范式，不进行方法重叠分析。',
              metrics: { required_paradigm: 'STEM' },
            },
            is_degraded: false,
          },
        ],
      },
      meta: { request_id: 'req-insufficient-b' },
    } satisfies DataResponse<PatrolReport>)

    const wrapper = await mountPatrolView()
    await setPaperSelection(wrapper, 'hss-001', 'hss-002')
    await wrapper.find('.patrol-run-stub').trigger('click')
    await flushPromises()

    const warningCard = wrapper.find('[data-testid="insufficient-data-insight-card"]')
    expect(warningCard.exists()).toBe(true)
    expect(warningCard.text()).toContain(PATROL_BASELINE_COPY.insufficientInsightBadge)
    expect(warningCard.text()).toContain('范式不适用')
    expect(warningCard.text()).toContain('PARADIGM_GATE')
    expect(wrapper.find('.patrol-insight').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(PATROL_BASELINE_COPY.nodeRefGraphLink)
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

  describe('F10 four-mode UI', () => {
    const v2Copy = patrolBaselineCopyV2()

    const modeCases: Array<{ label: string; mode: PatrolMode; paperA: string; paperB: string }> = [
      { label: PATROL_BASELINE_COPY.modeLensClashLabel, mode: 'lens_clash', paperA: 'hss-001', paperB: 'hss-002' },
      {
        label: PATROL_BASELINE_COPY.modeContradictionLabel,
        mode: 'contradiction',
        paperA: 'hss-001',
        paperB: 'hss-002',
      },
      { label: v2Copy.modeMethodOverlapLabel, mode: 'method_overlap', paperA: 'stem-001', paperB: 'stem-002' },
      { label: v2Copy.modeClaimEvolutionLabel, mode: 'claim_evolution', paperA: 'stem-001', paperB: 'stem-002' },
    ]

    it('renders four mode tabs with product labels and captions (functional)', async () => {
      const wrapper = await mountPatrolView()
      const tabs = wrapper.findAll('.patrol-mode-segment__item')

      expect(tabs).toHaveLength(4)
      expect(PATROL_MODE_OPTIONS).toHaveLength(4)
      for (const option of PATROL_MODE_OPTIONS) {
        expect(wrapper.text()).toContain(option.label)
        expect(wrapper.text()).toContain(option.caption)
      }
    })

    it.each(modeCases)(
      'forwards selected mode $mode in runPatrol body (接口/functional)',
      async ({ label, mode, paperA, paperB }) => {
        mockRunPatrol.mockResolvedValue(patrolReport)

        const wrapper = await mountPatrolView()
        await setPaperSelection(wrapper, paperA, paperB)
        await selectModeByLabel(wrapper, label)
        await wrapper.find('.patrol-run-stub').trigger('click')
        await flushPromises()

        expect(mockRunPatrol).toHaveBeenCalledWith([paperA, paperB], { mode })
      },
    )

    it('renders method_overlap structured_points fields from fixture (functional/snapshot-shape)', async () => {
      mockRunPatrol.mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

      const wrapper = await mountPatrolView()
      await setPaperSelection(wrapper, 'stem-001', 'stem-002')
      await selectModeByLabel(wrapper, v2Copy.modeMethodOverlapLabel)
      await wrapper.find('.patrol-run-stub').trigger('click')
      await flushPromises()

      const pointsRoot = wrapper.find('[data-testid="patrol-structured-points"]')
      expect(pointsRoot.exists()).toBe(true)
      expect(pointsRoot.text()).toContain('PCA')
      expect(pointsRoot.text()).toContain('MNIST')
      expect(pointsRoot.html()).toContain('patrol-point-card--method_overlap')
    })

    it('keeps default active tab at lens_clash before user interaction (boundary)', async () => {
      const wrapper = await mountPatrolView()
      const active = wrapper.find('.patrol-mode-segment__item--active')

      expect(active.text()).toContain(PATROL_BASELINE_COPY.modeLensClashLabel)
      expect(active.text()).not.toContain(v2Copy.modeMethodOverlapLabel)
    })

    it('keeps exactly four mode tabs after cycling every production option (越权/边界)', async () => {
      const wrapper = await mountPatrolView()
      for (const option of PATROL_MODE_OPTIONS) {
        await selectModeByLabel(wrapper, option.label)
        expect(wrapper.findAll('.patrol-mode-segment__item')).toHaveLength(4)
        expect(wrapper.find('.patrol-mode-segment__item--active').text()).toContain(option.label)
      }
      expect(wrapper.findAll('.patrol-mode-segment__item').map((t) => t.text())).toEqual(
        expect.arrayContaining(PATROL_MODE_OPTIONS.map((o) => expect.stringContaining(o.label))),
      )
    })
  })
})
