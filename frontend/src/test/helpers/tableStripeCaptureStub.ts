/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { defineComponent, h, type PropType } from 'vue'

export interface TableStripeCapture {
  stripe: boolean
  tableClass: string
}

/** Captures el-table stripe + class props for layout acceptance tests. */
export function createTableStripeCapture(onCapture: (state: TableStripeCapture) => void) {
  return defineComponent({
    props: {
      stripe: Boolean,
      class: {
        type: [String, Array, Object] as PropType<string | string[] | Record<string, boolean>>,
        default: '',
      },
      data: {
        type: Array,
        default: () => [],
      },
    },
    setup(props) {
      onCapture({
        stripe: Boolean(props.stripe),
        tableClass: String(props.class ?? ''),
      })
      return () => h('div', { class: 'table-stub' })
    },
  })
}
