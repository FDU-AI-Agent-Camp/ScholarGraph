<script setup lang="ts">
import { Graph, NodeEvent, type IElementEvent } from '@antv/g6'
import { onMounted, onUnmounted, ref, watch } from 'vue'

import type { UnifiedPaperGraph } from '@/api/types'
import { cssToken } from '@/utils/cssTokens'
import { buildHighlightStateMap, getGraphNodeTypeColor, toG6GraphPayload } from '@/utils/paperGraph'

import GraphLegend from './GraphLegend.vue'

const DEFAULT_HEIGHT = 480
const COMPACT_HEIGHT = 320

const props = withDefaults(
  defineProps<{
    graph: UnifiedPaperGraph | null
    highlightNodeId?: string | null
    compact?: boolean
  }>(),
  {
    highlightNodeId: null,
    compact: false,
  },
)

const emit = defineEmits<{
  nodeClick: [nodeId: string]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let graphInstance: Graph | null = null
let resizeObserver: ResizeObserver | null = null

const graphHeight = () => (props.compact ? COMPACT_HEIGHT : DEFAULT_HEIGHT)

function nodeLabelText(datum: { data?: { label?: string; nodeType?: string } }): string {
  const label = datum.data?.label ?? ''
  const nodeType = datum.data?.nodeType
  return nodeType ? `${label}\n(${nodeType})` : label
}

function createGraphInstance(): Graph | null {
  if (!containerRef.value || !props.graph) {
    return null
  }

  const width = containerRef.value.clientWidth || 800
  const payload = toG6GraphPayload(props.graph)
  const nodeFill = cssToken('--color-primary', '#0d6e6e')
  const nodeStroke = cssToken('--color-primary-hover', '#0a5858')
  const activeFill = cssToken('--color-citation-active-bg', '#fff1f2')
  const activeStroke = cssToken('--color-citation-active', '#e11d48')
  const payloadWithColors = {
    ...payload,
    nodes: payload.nodes.map((node) => {
      const nodeType = String(node.data.nodeType ?? '')
      return {
        ...node,
        data: {
          ...node.data,
          fill: getGraphNodeTypeColor(nodeType, props.graph?.paradigm),
        },
      }
    }),
  }

  return new Graph({
    container: containerRef.value,
    width,
    height: graphHeight(),
    data: payloadWithColors,
    layout: {
      type: 'dagre',
      rankdir: 'TB',
      nodesep: 36,
      ranksep: 48,
    },
    node: {
      style: {
        size: 40,
        labelText: nodeLabelText,
        labelWordWrap: true,
        labelMaxWidth: 140,
        fill: (datum: { data?: { fill?: string } }) => datum.data?.fill ?? nodeFill,
        stroke: nodeStroke,
        lineWidth: 1,
      },
      state: {
        active: {
          fill: activeFill,
          stroke: activeStroke,
          lineWidth: 3,
        },
      },
    },
    edge: {
      style: {
        labelText: (datum: { data?: { label?: string } }) => datum.data?.label ?? '',
        endArrow: true,
      },
    },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element', 'click-select'],
  })
}

async function applyHighlight(nodeId: string | null | undefined): Promise<void> {
  if (!graphInstance || !props.graph) {
    return
  }
  const nodeIds = props.graph.nodes.map((node) => node.id)
  await graphInstance.setElementState(buildHighlightStateMap(nodeIds, nodeId))
  if (nodeId) {
    await graphInstance.focusElement(nodeId)
  }
}

async function renderGraph(): Promise<void> {
  graphInstance?.destroy()
  graphInstance = createGraphInstance()
  if (!graphInstance) {
    return
  }
  graphInstance.on(NodeEvent.CLICK, (event: IElementEvent) => {
    const nodeId = event.target?.id
    if (typeof nodeId === 'string' && nodeId.length > 0) {
      emit('nodeClick', nodeId)
    }
  })
  await graphInstance.render()
  await applyHighlight(props.highlightNodeId)
}

function resizeGraph(): void {
  if (!graphInstance || !containerRef.value) {
    return
  }
  graphInstance.setSize(containerRef.value.clientWidth || 800, graphHeight())
}

onMounted(() => {
  void renderGraph()
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => resizeGraph())
    resizeObserver.observe(containerRef.value)
  }
})

watch(
  () => props.graph,
  () => {
    void renderGraph()
  },
)

watch(
  () => props.highlightNodeId,
  (nodeId) => {
    void applyHighlight(nodeId)
  },
)

watch(
  () => props.compact,
  () => {
    resizeGraph()
  },
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  graphInstance?.destroy()
  graphInstance = null
})
</script>

<template>
  <div v-if="!graph" class="placeholder">暂无图谱数据</div>
  <div v-else class="paper-graph" :class="{ compact }">
    <div ref="containerRef" class="graph-host" :class="{ compact }" />
    <GraphLegend v-if="compact" :graph="graph" class="paper-graph__legend" />
  </div>
</template>

<style scoped>
.paper-graph {
  position: relative;
  width: 100%;
}

.paper-graph__legend {
  position: absolute;
  left: var(--spacing-16);
  bottom: var(--spacing-16);
  z-index: var(--z-card);
  max-width: calc(100% - var(--spacing-32));
}

.graph-host,
.placeholder {
  width: 100%;
  min-height: 480px;
  background: var(--color-bg-canvas);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-lg);
}

.graph-host.compact {
  min-height: 320px;
  border: none;
  border-radius: var(--radius-xl);
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}
</style>
