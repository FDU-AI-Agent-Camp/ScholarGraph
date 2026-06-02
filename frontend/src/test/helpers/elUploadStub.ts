import type { UploadRequestOptions } from 'element-plus'
import { defineComponent, type PropType } from 'vue'

import { triggerPdfUpload } from '@/test/helpers/uploadStubUtils'

/** el-upload stub that fires a PDF upload through httpRequest. */
export const elUploadStub = defineComponent({
  props: {
    httpRequest: {
      type: Function as PropType<(options: UploadRequestOptions) => void>,
      required: true,
    },
  },
  setup(props) {
    function run() {
      triggerPdfUpload(props.httpRequest)
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
