/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import * as papersApi from '@/api/papers'
import type { DataResponse, PaperStatusData } from '@/api/types'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import failedStatusEnvelope from '../../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import processingStatusEnvelope from '../../../../docs/api/fixtures/paper-status-hss-002.json'

const failedStatusResponse = failedStatusEnvelope as DataResponse<PaperStatusData>
const processingStatusResponse = processingStatusEnvelope as DataResponse<PaperStatusData>

vi.mock('@/api/papers', () => ({
  getPaperStatus: vi.fn(),
}))

describe('PaperStatusPanel integration (API mock fixture)', () => {
  it('displays failed paper status from docs/api fixture envelope', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(failedStatusResponse)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-failed-001', autoStart: true },
    })
    await flushPromises()

    expect(papersApi.getPaperStatus).toHaveBeenCalledWith('hss-failed-001')
    const alert = wrapper.find('.el-alert-stub')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-title')).toBe('LLM_JSON_INVALID')
    expect(alert.attributes('data-description')).toBe(failedStatusResponse.data.message)
    expect(wrapper.text()).toContain('失败阶段')
    expect(wrapper.text()).toContain('classifying')
    expect(wrapper.text()).toContain('范式分类')
  })

  it('shows plain message for processing fixture without failure alert', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(processingStatusResponse)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-002', autoStart: true },
    })
    await flushPromises()

    expect(wrapper.find('.el-alert-stub').exists()).toBe(false)
    expect(wrapper.text()).toContain(processingStatusResponse.data.message)
    expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.refreshCaption)
    expect(wrapper.text()).toContain('范式分类')
  })
})
