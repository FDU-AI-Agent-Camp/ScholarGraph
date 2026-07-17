/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import type { UploadRequestOptions } from 'element-plus'
import { defineComponent, h, type PropType } from 'vue'

import { triggerPdfUpload } from '@/test/helpers/uploadStubUtils'

/** el-upload stub with default slot support (uploading state tests). */
export const uploadWithSlotStub = defineComponent({
  props: {
    httpRequest: {
      type: Function as PropType<(options: UploadRequestOptions) => void>,
      required: true,
    },
  },
  setup(props, { slots }) {
    function run() {
      triggerPdfUpload(props.httpRequest)
    }
    return () => h('div', [h('button', { class: 'do-upload', onClick: run }, 'upload'), slots.default?.()])
  },
})
