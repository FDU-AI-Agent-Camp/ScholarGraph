/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * §14.6 — PaperStatusPanel.vue 与 usePaperStatus / client 链路的冒烟测试。
 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import * as papersApi from '@/api/papers'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import type { DataResponse, PaperStatusData } from '@/api/types'
import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'

vi.mock('@/api/papers', () => ({
  getPaperStatus: vi.fn(),
}))

const failedResponse = failedStatusEnvelope as DataResponse<PaperStatusData>

describe('PaperStatusPanel key path (§14.6)', () => {
  it('renders failed status from canonical openapi fixture via papers API', async () => {
    vi.mocked(papersApi.getPaperStatus).mockResolvedValue(failedResponse)

    const wrapper = mount(PaperStatusPanel, {
      props: { paperId: 'hss-failed-001', autoStart: true },
    })
    await flushPromises()

    expect(papersApi.getPaperStatus).toHaveBeenCalledWith('hss-failed-001')
    const alert = wrapper.find('.el-alert-stub')
    expect(alert.attributes('data-title')).toBe('LLM_JSON_INVALID')
    expect(wrapper.text()).toContain('classifying')
  })
})
