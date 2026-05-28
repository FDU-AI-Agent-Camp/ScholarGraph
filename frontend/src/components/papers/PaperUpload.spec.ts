import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'

const mockUploadPaper = vi.hoisted(() => vi.fn())
const elMessageError = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: vi.fn(),
    success: vi.fn(),
    error: (...args: unknown[]) => elMessageError(...args),
  },
}))

import PaperUpload from '@/components/papers/PaperUpload.vue'

const ElUploadStub = defineComponent({
  props: {
    httpRequest: {
      type: Function,
      required: true,
    },
  },
  setup(props) {
    function run() {
      const file = new File(['%PDF'], 'sample.pdf', { type: 'application/pdf' })
      void props.httpRequest({ file, onSuccess: vi.fn() })
    }
    return { run }
  },
  template: '<button class="do-upload" @click="run">upload</button>',
})

describe('PaperUpload', () => {
  it('surfaces ApiClientError message on upload failure', async () => {
    mockUploadPaper.mockRejectedValue(new ApiClientError({ code: 'INGEST_FAILED', message: '无法解析 PDF' }, 400))

    const wrapper = mount(PaperUpload, {
      global: {
        stubs: { 'el-upload': ElUploadStub, 'el-icon': true },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    expect(elMessageError).toHaveBeenCalledWith('无法解析 PDF')
  })
})
