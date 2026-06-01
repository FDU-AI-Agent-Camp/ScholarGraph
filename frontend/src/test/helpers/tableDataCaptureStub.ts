import { defineComponent, h, type PropType } from 'vue'

import type { PaperSummary } from '@/api/types'

/** Captures el-table :data binding for PapersView store wiring tests. */
export function createTableDataCapture(onCapture: (rows: PaperSummary[]) => void) {
  return defineComponent({
    props: {
      data: {
        type: Array as PropType<PaperSummary[]>,
        default: () => [],
      },
    },
    setup(props) {
      onCapture(props.data)
      return () => h('div', { class: 'table-stub' })
    },
  })
}
