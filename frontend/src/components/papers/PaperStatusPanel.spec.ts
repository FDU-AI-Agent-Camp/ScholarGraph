import { ElMessage, ElMessageBox } from 'element-plus'
import type { MessageBoxData } from 'element-plus'
import { ref } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { EXTRACT_HEURISTIC_FALLBACK_MESSAGE, EXTRACT_HEURISTIC_FALLBACK_CODE } from '@/utils/extractWarnings'
import { CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE } from '@/utils/classifyWarnings'
import {
  failedStatus,
  failedStatusProcessOrphaned,
  failedStatusProcessTimeout,
  failedStatusQueueTimeout,
  failedStatusWithoutCode,
  indexingStatus,
  processingStatus,
  readyStatus,
  readyStatusWithBothFallbacks,
  readyStatusWithClassifyFallback,
  readyStatusWithExtractFallback,
  readyWithWarningsStatus,
  classifyingStatusWithClassifyFallback,
} from '@/test/fixtures/paperStatus'
import { PROCESS_ORPHANED_TITLE, PROCESS_TIMEOUT_TITLE, QUEUE_TIMEOUT_TITLE } from '@/utils/pipelineFailureCopy'

const mockStart = vi.fn()
const mockStop = vi.fn()
const mockPollOnce = vi.fn()
const mockStatus = ref<typeof processingStatus | null>(null)
const mockPolling = ref(false)
const mockForceReextract = vi.fn()

vi.mock('@/composables/usePaperStatus', () => ({
  usePaperStatus: () => ({
    status: mockStatus,
    polling: mockPolling,
    start: mockStart,
    stop: mockStop,
    pollOnce: mockPollOnce,
  }),
}))

vi.mock('@/api/papers', () => ({
  forceReextractPaper: (...args: unknown[]) => mockForceReextract(...args),
}))

enableAutoUnmount(afterEach)

describe('PaperStatusPanel', () => {
  beforeEach(() => {
    vi.mocked(ElMessage.warning).mockClear()
    vi.mocked(ElMessage.success).mockClear()
    vi.mocked(ElMessage.error).mockClear()
    vi.mocked(ElMessageBox.confirm).mockReset()
    mockForceReextract.mockReset()
    mockStart.mockClear()
    mockStop.mockClear()
    mockPollOnce.mockClear()
    mockStatus.value = null
    mockPolling.value = false
  })

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
    expect(wrapper.findAll('.status-panel__step')).toHaveLength(6)
  })

  it('marks all steps done when status is ready', () => {
    mockStatus.value = readyStatus

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.findAll('.status-panel__step--done')).toHaveLength(6)
    expect(wrapper.find('.status-panel__step--active').exists()).toBe(false)
    expect(wrapper.find('.status-panel__check').exists()).toBe(true)
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

  it.each([
    {
      name: 'PROCESS_ORPHANED',
      status: failedStatusProcessOrphaned,
      title: PROCESS_ORPHANED_TITLE,
    },
    {
      name: 'PROCESS_TIMEOUT',
      status: failedStatusProcessTimeout,
      title: PROCESS_TIMEOUT_TITLE,
    },
    {
      name: 'QUEUE_TIMEOUT',
      status: failedStatusQueueTimeout,
      title: QUEUE_TIMEOUT_TITLE,
    },
  ])('maps $name failure code to Chinese title with backend message', ({ status, title }) => {
    mockStatus.value = status
    mockPolling.value = false

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: status.paper_id, autoStart: false },
    })

    const alert = wrapper.find('.el-alert-stub')
    expect(alert.attributes('data-title')).toBe(title)
    expect(alert.attributes('data-description')).toBe(status.message)
  })

  it('emits ready when status becomes ready', async () => {
    mockStatus.value = processingStatus
    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    mockStatus.value = readyStatus
    await flushPromises()

    expect(wrapper.emitted('ready')).toHaveLength(1)
    expect(wrapper.emitted('terminalReached')).toEqual([['ready']])
  })

  it('emits terminalReached for ready_with_warnings so detail can rehydrate (G1)', async () => {
    mockStatus.value = processingStatus
    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    mockStatus.value = readyWithWarningsStatus
    await flushPromises()

    expect(wrapper.emitted('terminalReached')).toEqual([['ready_with_warnings']])
    expect(wrapper.emitted('ready')).toBeUndefined()
  })

  it('calls start on mount when autoStart is true', () => {
    mockStart.mockClear()
    mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: true },
    })
    expect(mockStart).toHaveBeenCalled()
  })

  it('renders extract fallback warning alert when extract_warnings present', () => {
    mockStatus.value = {
      ...readyStatus,
      extract_warnings: [EXTRACT_HEURISTIC_FALLBACK_CODE],
    }

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    const alerts = wrapper.findAll('.el-alert-stub')
    const warning = alerts.find((node) => node.attributes('data-type') === 'warning')
    expect(warning?.attributes('data-title')).toBe(EXTRACT_HEURISTIC_FALLBACK_MESSAGE)
  })

  it('does not render extract warning alert when extract_warnings empty', () => {
    mockStatus.value = readyStatus

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    const warning = wrapper.findAll('.el-alert-stub').find((node) => node.attributes('data-type') === 'warning')
    expect(warning).toBeUndefined()
  })

  it('shows ElMessage.warning once when polling reaches ready with extract fallback', async () => {
    vi.mocked(ElMessage.warning).mockClear()
    mockStatus.value = processingStatus
    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    mockStatus.value = readyStatusWithExtractFallback
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledTimes(1)
    expect(ElMessage.warning).toHaveBeenCalledWith(EXTRACT_HEURISTIC_FALLBACK_MESSAGE)
    expect(wrapper.emitted('ready')).toHaveLength(1)
  })

  it('renders classify fallback warning alert when classify_warnings present', () => {
    mockStatus.value = readyStatusWithClassifyFallback

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    const alerts = wrapper.findAll('.el-alert-stub')
    const warning = alerts.find((node) => node.attributes('data-type') === 'warning')
    expect(warning?.attributes('data-title')).toBe(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
    expect(wrapper.find('.status-panel__classify-warning').exists()).toBe(true)
  })

  it('does not render classify warning alert when classify_warnings empty', () => {
    mockStatus.value = readyStatus

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.find('.status-panel__classify-warning').exists()).toBe(false)
  })

  it('shows ElMessage.warning once when polling reaches ready with classify fallback', async () => {
    vi.mocked(ElMessage.warning).mockClear()
    mockStatus.value = processingStatus
    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    mockStatus.value = readyStatusWithClassifyFallback
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledTimes(1)
    expect(ElMessage.warning).toHaveBeenCalledWith(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
    expect(wrapper.emitted('ready')).toHaveLength(1)
  })

  it('shows classify warning alert while polling during classifying stage', () => {
    mockStatus.value = classifyingStatusWithClassifyFallback

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.find('.status-panel__classify-warning').exists()).toBe(true)
    const warning = wrapper.findAll('.el-alert-stub').find((node) => node.attributes('data-type') === 'warning')
    expect(warning?.attributes('data-title')).toBe(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
    expect(ElMessage.warning).not.toHaveBeenCalled()
  })

  it('renders classify and extract fallback alerts together when both warnings present', () => {
    mockStatus.value = readyStatusWithBothFallbacks

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.find('.status-panel__classify-warning').exists()).toBe(true)
    expect(wrapper.find('.status-panel__extract-warning').exists()).toBe(true)
    const warnings = wrapper.findAll('.el-alert-stub').filter((node) => node.attributes('data-type') === 'warning')
    expect(warnings).toHaveLength(2)
    expect(warnings.map((node) => node.attributes('data-title'))).toEqual([
      CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
      EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })

  it('shows pause/resume refresh labels instead of polling jargon', () => {
    mockStatus.value = processingStatus
    mockPolling.value = true

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })

    expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.pauseRefresh)
    expect(wrapper.text()).not.toContain('轮询')

    mockPolling.value = false
    const paused = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })
    expect(paused.text()).toContain(DETAIL_BASELINE_COPY.resumeRefresh)
    expect(paused.text()).not.toContain('轮询')
  })

  it('force-confirms then reextracts with force=true while processing', async () => {
    mockStatus.value = processingStatus
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as MessageBoxData)
    mockForceReextract.mockResolvedValue({
      data: { ...processingStatus, status: 'pending', percent: 0, stage: null, message: 'queued' },
      meta: { request_id: 'req-re' },
    })

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-001', autoStart: false },
    })
    await wrapper.get('[data-testid="reextract-button"]').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(mockForceReextract).toHaveBeenCalledWith('paper-001', { force: true })
    expect(ElMessage.success).toHaveBeenCalledWith(DETAIL_BASELINE_COPY.reextractSuccess)
    expect(mockStart).toHaveBeenCalled()
  })

  it('force-confirms then reextracts with force=true while indexing', async () => {
    mockStatus.value = indexingStatus
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as MessageBoxData)
    mockForceReextract.mockResolvedValue({
      data: { ...indexingStatus, status: 'pending', percent: 0, stage: null, message: 'queued' },
      meta: { request_id: 'req-re-idx' },
    })

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-idx', autoStart: false },
    })
    await wrapper.get('[data-testid="reextract-button"]').trigger('click')
    await flushPromises()

    expect(mockForceReextract).toHaveBeenCalledWith('paper-idx', { force: true })
  })

  it('retries with force=true after 409 on ready reextract race', async () => {
    mockStatus.value = readyStatus
    mockForceReextract
      .mockRejectedValueOnce(new ApiClientError({ code: 'PAPER_ALREADY_PROCESSING', message: 'busy' }, 409))
      .mockResolvedValueOnce({
        data: { ...readyStatus, status: 'pending', percent: 0, stage: null, message: 'queued' },
        meta: { request_id: 'req-retry' },
      })
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as MessageBoxData)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'paper-ready', autoStart: false },
    })
    await wrapper.get('[data-testid="reextract-button"]').trigger('click')
    await flushPromises()

    expect(mockForceReextract).toHaveBeenNthCalledWith(1, 'paper-ready', { force: false })
    expect(mockForceReextract).toHaveBeenNthCalledWith(2, 'paper-ready', { force: true })
  })
})
