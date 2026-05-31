import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { PAPERS_BASELINE_COPY } from '@/test/helpers/papersBaselineCopy'

const mockUploadPaper = vi.hoisted(() => vi.fn())
const elMessageWarning = vi.hoisted(() => vi.fn())
const elMessageError = vi.hoisted(() => vi.fn())
const elMessageSuccess = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    warning: (...args: unknown[]) => elMessageWarning(...args),
    success: (...args: unknown[]) => elMessageSuccess(...args),
    error: (...args: unknown[]) => elMessageError(...args),
  },
}))

import PaperUpload from '@/components/papers/PaperUpload.vue'

const globalStubs = {
  'el-icon': true,
  'el-progress': true,
  'el-alert': {
    props: ['title', 'type'],
    template: '<div class="el-alert-stub" :data-title="title" :data-type="type" />',
  },
}

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
      void props.httpRequest({ file, onSuccess: vi.fn(), onError: vi.fn() })
    }
    return { run }
  },
  template: `
    <div>
      <button class="do-upload" @click="run">upload</button>
      <slot />
    </div>
  `,
})

describe('PaperUpload', () => {
  beforeEach(() => {
    mockUploadPaper.mockReset()
    elMessageWarning.mockClear()
    elMessageError.mockClear()
    elMessageSuccess.mockClear()
  })

  describe('§1.4.4 upload baseline copy', () => {
    it('renders main copy, emphasized click label, and tip', () => {
      const wrapper = mount(PaperUpload, {
        global: {
          stubs: {
            ...globalStubs,
            'el-upload': {
              template: `
                <div class="upload-stub">
                  <p class="paper-upload__text text-body">
                    ${PAPERS_BASELINE_COPY.uploadMain}
                    <em>${PAPERS_BASELINE_COPY.uploadClick}</em>
                  </p>
                </div>
              `,
            },
          },
        },
      })

      expect(wrapper.find('.paper-upload__text').text()).toContain(PAPERS_BASELINE_COPY.uploadMain)
      expect(wrapper.find('.paper-upload__text em').text()).toBe(PAPERS_BASELINE_COPY.uploadClick)
      expect(wrapper.find('.paper-upload__tip').text()).toBe(PAPERS_BASELINE_COPY.uploadTip)
    })
  })

  it('surfaces INGEST_FAILED as inline alert with API message', async () => {
    mockUploadPaper.mockRejectedValue(new ApiClientError({ code: 'INGEST_FAILED', message: '无法解析 PDF' }, 400))

    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          ...globalStubs,
          'el-upload': ElUploadStub,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.el-alert-stub')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-title')).toBe('无法解析 PDF')
    expect(alert.attributes('data-type')).toBe('error')
    expect(elMessageError).not.toHaveBeenCalled()
  })

  it('shows uploading label and filename while request is in flight', async () => {
    let resolveUpload: ((value: unknown) => void) | undefined
    mockUploadPaper.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpload = resolve
        }),
    )

    const UploadWithSlotStub = defineComponent({
      props: {
        httpRequest: {
          type: Function,
          required: true,
        },
      },
      setup(props, { slots }) {
        function run() {
          const file = new File(['%PDF'], 'sample.pdf', { type: 'application/pdf' })
          void props.httpRequest({ file, onSuccess: vi.fn(), onError: vi.fn() })
        }
        return () => h('div', [h('button', { class: 'do-upload', onClick: run }, 'upload'), slots.default?.()])
      },
    })

    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          ...globalStubs,
          'el-upload': UploadWithSlotStub,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    expect(wrapper.find('.paper-upload__status').text()).toBe(PAPERS_BASELINE_COPY.uploading)
    expect(wrapper.find('.paper-upload__filename').text()).toBe('sample.pdf')

    resolveUpload?.({
      data: { paper_id: 'new-id', message: '上传成功' },
    })
    await flushPromises()
  })

  it('emits uploaded with paper_id on success', async () => {
    mockUploadPaper.mockResolvedValue({
      data: { paper_id: 'stem-001', message: '上传成功，已进入解构流水线' },
    })

    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          ...globalStubs,
          'el-upload': ElUploadStub,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('uploaded')).toEqual([['stem-001']])
    expect(elMessageSuccess).toHaveBeenCalledWith('上传成功，已进入解构流水线')
  })

  it('warns when file is not PDF', async () => {
    const UploadNonPdfStub = defineComponent({
      props: {
        httpRequest: {
          type: Function,
          required: true,
        },
      },
      setup(props) {
        function run() {
          const file = new File(['text'], 'notes.txt', { type: 'text/plain' })
          void props.httpRequest({ file, onSuccess: vi.fn(), onError: vi.fn() })
        }
        return { run }
      },
      template: '<button class="do-upload" @click="run">upload</button>',
    })

    const wrapper = mount(PaperUpload, {
      global: {
        stubs: {
          ...globalStubs,
          'el-upload': UploadNonPdfStub,
        },
      },
    })

    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    expect(elMessageWarning).toHaveBeenCalledWith('请上传 PDF 文件')
    expect(mockUploadPaper).not.toHaveBeenCalled()
  })
})
