/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import type { UploadRequestOptions } from 'element-plus'
import { defineComponent, type PropType } from 'vue'

import { triggerNonPdfUpload } from '@/test/helpers/uploadStubUtils'

/** el-upload stub that submits a non-PDF file. */
export const uploadNonPdfStub = defineComponent({
  props: {
    httpRequest: {
      type: Function as PropType<(options: UploadRequestOptions) => void>,
      required: true,
    },
  },
  setup(props) {
    function run() {
      triggerNonPdfUpload(props.httpRequest)
    }
    return { run }
  },
  template: '<button class="do-upload" @click="run">upload</button>',
})
