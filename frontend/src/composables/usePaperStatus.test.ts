import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as papersApi from '@/api/papers'
import { usePaperStatus, type UsePaperStatusReturn } from '@/composables/usePaperStatus'
import type { DataResponse, PaperStatusData } from '@/api/types'
import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import {
  failedStatus,
  processingStatus,
  readyStatus,
  statusResponse,
} from '@/test/fixtures/paperStatus'

const failedStatusResponse = failedStatusEnvelope as DataResponse<PaperStatusData>

vi.mock('@/api/papers', () => ({
  getPaperStatus: vi.fn(),
}))

function mountComposable(paperId: string, intervalMs = 2000) {
  let exposed: ReturnType<typeof usePaperStatus> | undefined
  const Host = defineComponent({
    setup() {
      exposed = usePaperStatus(paperId, intervalMs)
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return {
    wrapper,
    api: exposed!,
  }
}

describe('usePaperStatus', () => {
  it('exposes UsePaperStatusReturn from composable', () => {
    const { api, wrapper } = mountComposable('paper-typed')
    const typed: UsePaperStatusReturn = api
    expect(typed.status.value).toBeNull()
    expect(typed.polling.value).toBe(false)
    expect(typed.pollOnce).toBeTypeOf('function')
    wrapper.unmount()
  })

  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(papersApi.getPaperStatus).mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('pollOnce updates status from API envelope', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(statusResponse(processingStatus))
    const { api, wrapper } = mountComposable('paper-001')

    await api.pollOnce()
    await flushPromises()

    expect(papersApi.getPaperStatus).toHaveBeenCalledWith('paper-001')
    expect(api.status.value).toEqual(processingStatus)
    expect(api.polling.value).toBe(false)
    wrapper.unmount()
  })

  it('start stops polling when status is terminal (failed)', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(statusResponse(failedStatus))
    const { api, wrapper } = mountComposable('paper-001')

    api.start()
    await flushPromises()

    expect(api.status.value?.status).toBe('failed')
    expect(api.polling.value).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
    wrapper.unmount()
  })

  it('preserves error_code and failed_during from docs fixture envelope', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(failedStatusResponse)
    const { api, wrapper } = mountComposable('hss-failed-001')

    await api.pollOnce()
    await flushPromises()

    expect(api.status.value).toMatchObject({
      paper_id: 'hss-failed-001',
      status: 'failed',
      error_code: 'LLM_JSON_INVALID',
      failed_during: 'classifying',
    })
    wrapper.unmount()
  })

  it('start stops polling when status is terminal (ready)', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(statusResponse(readyStatus))
    const { api, wrapper } = mountComposable('paper-001')

    api.start()
    await flushPromises()

    expect(api.status.value?.status).toBe('ready')
    expect(api.polling.value).toBe(false)
    wrapper.unmount()
  })

  it('keeps polling while status is processing and polls on interval', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(statusResponse(processingStatus))
    const { api, wrapper } = mountComposable('paper-001', 1000)

    api.start()
    await flushPromises()
    expect(api.polling.value).toBe(true)
    expect(papersApi.getPaperStatus).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(papersApi.getPaperStatus).toHaveBeenCalledTimes(2)

    api.stop()
    wrapper.unmount()
  })

  it('stop clears interval without further polls', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(statusResponse(processingStatus))
    const { api, wrapper } = mountComposable('paper-001', 1000)

    api.start()
    await flushPromises()
    api.stop()

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(papersApi.getPaperStatus).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
