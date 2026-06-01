import { defineComponent, type PropType } from 'vue'

import type { UnifiedPaperGraph } from '@/api/types'

/** Lightweight PaperGraph stand-in for route smoke tests (avoids G6). */
export const paperGraphSmokeStub = defineComponent({
  name: 'PaperGraph',
  props: {
    graph: {
      type: Object as PropType<UnifiedPaperGraph | null>,
      default: null,
    },
    highlightNodeId: {
      type: String,
      default: undefined,
    },
    compact: {
      type: Boolean,
      default: false,
    },
    fullBleed: {
      type: Boolean,
      default: false,
    },
  },
  template: '<div class="paper-graph-smoke-stub" />',
})
