/**
 * Upload → pipeline status contract (FE mocks aligned with POST /papers + scheduler).
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as papersApi from '@/api/papers'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import PaperUpload from '@/components/papers/PaperUpload.vue'
import { elUploadStub } from '@/test/helpers/elUploadStub'

const mockUploadPaper = vi.fn()

vi.mock('@/api/papers', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/papers')>()
  return {
    ...actual,
    uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
  }
})

const elMessageSuccess = vi.hoisted(() => vi.fn())

vi.mock('element-plus', () => ({
  ElMessage: {
    success: elMessageSuccess,
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

describe('upload pipeline — PaperUpload contract', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    elMessageSuccess.mockClear()
    mockUploadPaper.mockReset()
    mockUploadPaper.mockResolvedValue({
      data: {
        paper_id: 'pipeline-paper-001',
        status: 'pending',
        message: '已接收 PDF，正在自动解构…',
      },
      meta: { request_id: 'upload-pipeline' },
    })
  })

  it('emits uploaded with paper_id from POST /papers envelope', async () => {
    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          'el-upload': elUploadStub,
          'el-icon': true,
          'el-progress': true,
          'el-alert': true,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    expect(mockUploadPaper).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('uploaded')).toEqual([['pipeline-paper-001']])
    expect(elMessageSuccess).toHaveBeenCalledWith(PAPERS_BASELINE_COPY.uploadSuccess)
  })

  it('uploadPaper sends multipart field file', async () => {
    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          'el-upload': elUploadStub,
          'el-icon': true,
          'el-progress': true,
          'el-alert': true,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    const file = mockUploadPaper.mock.calls[0]?.[0] as File
    expect(file.name).toBe('sample.pdf')
    expect(file.type).toBe('application/pdf')
  })
})
