import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { failedStatus, failedStatusWithoutCode, processingStatus, readyStatus } from '@/test/fixtures/paperStatus'

const mockStart = vi.fn()
const mockStop = vi.fn()
const mockStatus = ref<typeof processingStatus | null>(null)
const mockPolling = ref(false)

vi.mock('@/composables/usePaperStatus', () => ({
  usePaperStatus: () => ({
    status: mockStatus,
    polling: mockPolling,
    start: mockStart,
    stop: mockStop,
    pollOnce: vi.fn(),
  }),
}))

describe('PaperStatusPanel', () => {
  it('renders stepper labels and refresh caption while processing', () => {
    mockStatus.value = processingStatus
    mockPolling.value = true

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.pipelineTitle)
    expect(wrapper.text()).toContain('正在解析 PDF')
    expect(wrapper.text()).toContain('范式分类')
    expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.refreshCaption)
    expect(wrapper.text()).toContain(processingStatus.message)
    expect(wrapper.find('.el-alert-stub').exists()).toBe(false)
  })

  it('uses 8px progress track styling hook', () => {
    mockStatus.value = processingStatus
    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })
    expect(wrapper.find('.status-panel__progress').exists()).toBe(true)
  })

  it('marks the current pipeline stage as active in the vertical stepper', () => {
    mockStatus.value = processingStatus

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    const activeSteps = wrapper.findAll('.status-panel__step--active')
    expect(activeSteps).toHaveLength(1)
    expect(activeSteps[0]?.text()).toContain('范式分类')
    expect(wrapper.findAll('.status-panel__step')).toHaveLength(5)
  })

  it('marks all steps done when status is ready', () => {
    mockStatus.value = readyStatus

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.findAll('.status-panel__step--done')).toHaveLength(5)
    expect(wrapper.find('.status-panel__step--active').exists()).toBe(false)
  })

  it('renders failed alert with error_code title and message description', () => {
    mockStatus.value = failedStatus
    mockPolling.value = false

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    const alert = wrapper.find('.el-alert-stub')
    expect(alert.attributes('data-title')).toBe('LLM_JSON_INVALID')
    expect(alert.attributes('data-description')).toBe(failedStatus.message)
    expect(wrapper.text()).toContain('classifying')
  })

  it('uses default error title when error_code is absent', () => {
    mockStatus.value = failedStatusWithoutCode
    mockPolling.value = false

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-002', autoStart: false },
    })

    expect(wrapper.find('.el-alert-stub').attributes('data-title')).toBe('PIPELINE_FAILED')
    expect(wrapper.find('.el-alert-stub').attributes('data-description')).toBe(failedStatusWithoutCode.message)
  })

  it('emits ready when status becomes ready', async () => {
    mockStatus.value = processingStatus
    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    mockStatus.value = readyStatus
    await flushPromises()

    expect(wrapper.emitted('ready')).toHaveLength(1)
  })

  it('calls start on mount when autoStart is true', () => {
    mockStart.mockClear()
    mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: true },
    })
    expect(mockStart).toHaveBeenCalled()
  })
})
