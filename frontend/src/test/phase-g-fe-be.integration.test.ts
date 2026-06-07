/**
 * G5 FE↔BE 联调：classify_warnings 机器码 → 冻结文案 → StatusPanel / DetailView。
 *
 * 与 tests/integration/test_phase_g_fe_be_integration.py 成对验收（test_phase_g_fe_be_integration.py）。
 */
import { flushPromises, mount, enableAutoUnmount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as client from '@/api/client'
import * as papersApi from '@/api/papers'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import type { DataResponse, PaperDetail, PaperStatusData } from '@/api/types'
import {
  CLASSIFIER_HEURISTIC_FALLBACK_CODE,
  CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
  resolveClassifyWarningMessages,
} from '@/utils/classifyWarnings'
import { statusResponse, processingStatus, classifyingStatusWithClassifyFallback } from '@/test/fixtures/paperStatus'

import classifyFallbackDetailFixture from '../../../docs/api/fixtures/paper-detail-classify-fallback.json'
import classifyFallbackStatusFixture from '../../../docs/api/fixtures/paper-status-classify-fallback.json'
import processingStatusFixture from '../../../docs/api/fixtures/paper-status-processing.json'

const mockStart = vi.fn()
const mockStop = vi.fn()
const mockStatus = ref<PaperStatusData | null>(null)
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

const elMessageWarning = vi.hoisted(() => vi.fn())

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: (...args: unknown[]) => elMessageWarning(...args),
  },
}))

const classifyFallbackStatus = classifyFallbackStatusFixture as DataResponse<PaperStatusData>
const classifyFallbackDetail = classifyFallbackDetailFixture as DataResponse<PaperDetail>
const processingEnvelope = processingStatusFixture as DataResponse<PaperStatusData>

afterEach(() => {
  vi.restoreAllMocks()
})

enableAutoUnmount(afterEach)

describe('Phase G FE↔BE classify fallback integration', () => {
  beforeEach(() => {
    elMessageWarning.mockClear()
    mockStatus.value = null
    mockPolling.value = false
  })

  it('maps OpenAPI fixture machine code to frozen user message for UI', () => {
    const codes = classifyFallbackStatus.data.classify_warnings
    expect(codes).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(resolveClassifyWarningMessages(codes)).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE])
    expect(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE).toBe('触发分类启发式Fallback!')
  })

  it('getPaperStatus parses classify-fallback fixture envelope', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(classifyFallbackStatus)

    const result = await papersApi.getPaperStatus('hss-classify-fallback-001')

    expect(result.data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(result.data.status).toBe('ready')
  })

  it('getPaper parses classify-fallback detail fixture with sibling classification', async () => {
    vi.spyOn(client, 'getData').mockResolvedValue(classifyFallbackDetail)

    const result = await papersApi.getPaper('hss-classify-fallback-001')

    expect(result.data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(result.data.classification?.paradigm).toBe('STEM')
    expect(Object.keys(result.data.classification ?? {})).toEqual(['paradigm', 'confidence', 'reason'])
  })

  it('PaperStatusPanel shows frozen alert while classifying with classify fallback', () => {
    mockStatus.value = classifyingStatusWithClassifyFallback

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-classify-fallback-001', autoStart: false },
    })

    const warning = wrapper
      .findAll('.el-alert-stub')
      .find((node) => node.attributes('data-type') === 'warning')
    expect(warning?.attributes('data-title')).toBe(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
    expect(wrapper.find('.status-panel__classify-warning').exists()).toBe(true)
    expect(elMessageWarning).not.toHaveBeenCalled()
  })

  it('PaperStatusPanel toast on ready transition mirrors BE status fixture', async () => {
    mockStatus.value = processingEnvelope.data
    mount(PaperStatusPanel, {
      props: { paperId: 'hss-classify-fallback-001', autoStart: false },
    })

    mockStatus.value = classifyFallbackStatus.data
    await flushPromises()

    expect(elMessageWarning).toHaveBeenCalledTimes(1)
    expect(elMessageWarning).toHaveBeenCalledWith(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
  })

  it('status fixture machine codes differ from user toast copy', () => {
    const codes = classifyFallbackStatus.data.classify_warnings ?? []
    const messages = resolveClassifyWarningMessages(codes)
    expect(codes).not.toContain(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
    expect(messages).toContain(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
  })

  it('processing → ready poll path uses statusResponse helper shape', () => {
    const readyWithFallback = statusResponse({
      ...processingStatus,
      status: 'ready',
      percent: 100,
      stage: 'ready',
      message: '建图完成',
      classify_warnings: [CLASSIFIER_HEURISTIC_FALLBACK_CODE],
    })
    expect(readyWithFallback.data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(resolveClassifyWarningMessages(readyWithFallback.data.classify_warnings)).toEqual([
      CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
    ])
  })
})
