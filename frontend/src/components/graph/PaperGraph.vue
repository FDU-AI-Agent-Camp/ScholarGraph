<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { Graph, NodeEvent, type IElementEvent } from '@antv/g6'
import { onMounted, onUnmounted, ref, watch } from 'vue'

import type { UnifiedPaperGraph } from '@/api/types'
import { cssToken } from '@/utils/cssTokens'
import {
  buildG6Behaviors,
  buildG6EdgeStyleOptions,
  buildG6FitViewPadding,
  buildG6GraphData,
  buildG6LayoutOptions,
  buildG6NodeStyleOptions,
  buildHighlightStateMap,
  GRAPH_COMPACT_HEIGHT,
  GRAPH_DEFAULT_HEIGHT,
  GRAPH_FIT_VIEW_DEBOUNCE_MS,
  GRAPH_FULL_MIN_HEIGHT,
  GRAPH_ZOOM_STEP,
  resolvePaperGraphThemeTokens,
} from '@/utils/paperGraph'

import GraphLegend from './GraphLegend.vue'

const props = withDefaults(
  defineProps<{
    graph: UnifiedPaperGraph | null
    highlightNodeId?: string | null
    compact?: boolean
    fullBleed?: boolean
  }>(),
  {
    highlightNodeId: null,
    compact: false,
    fullBleed: false,
  },
)

const emit = defineEmits<{
  nodeClick: [nodeId: string]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let graphInstance: Graph | null = null
let resizeObserver: ResizeObserver | null = null
let fitViewTimer: ReturnType<typeof setTimeout> | null = null

function viewportMode(): { compact: boolean; fullBleed: boolean } {
  return { compact: props.compact, fullBleed: props.fullBleed }
}

function graphHeight(): number {
  if (props.compact) {
    return GRAPH_COMPACT_HEIGHT
  }
  if (props.fullBleed && containerRef.value) {
    return Math.max(GRAPH_FULL_MIN_HEIGHT, containerRef.value.clientHeight)
  }
  return GRAPH_DEFAULT_HEIGHT
}

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
  const theme = resolvePaperGraphThemeTokens(cssToken)
  const nodeOptions = buildG6NodeStyleOptions(theme, nodeLabelText)

  return new Graph({
    container: containerRef.value,
    width,
    height: graphHeight(),
    padding: buildG6FitViewPadding(viewportMode()),
    data: buildG6GraphData(props.graph),
    layout: buildG6LayoutOptions({
      compact: props.compact,
      nodeCount: props.graph.nodes.length,
    }),
    node: nodeOptions,
    edge: buildG6EdgeStyleOptions(theme),
    behaviors: buildG6Behaviors(),
  })
}

function clearFitViewTimer(): void {
  if (fitViewTimer) {
    clearTimeout(fitViewTimer)
    fitViewTimer = null
  }
}

async function fitGraphView(): Promise<void> {
  if (!graphInstance) {
    return
  }
  graphInstance.setOptions({
    padding: buildG6FitViewPadding(viewportMode()),
  })
  await graphInstance.fitView()
}

function scheduleFitGraphView(): void {
  if (!graphInstance) {
    return
  }
  clearFitViewTimer()
  fitViewTimer = setTimeout(() => {
    fitViewTimer = null
    void fitGraphView()
  }, GRAPH_FIT_VIEW_DEBOUNCE_MS)
}

async function applyHighlight(nodeId: string | null | undefined): Promise<void> {
  if (!graphInstance || !props.graph) {
    return
  }
  const nodeIds = props.graph.nodes.map((node) => node.id)
  await graphInstance.setElementState(buildHighlightStateMap(nodeIds, nodeId))
  if (nodeId && props.fullBleed) {
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
  await fitGraphView()
  await applyHighlight(props.highlightNodeId)
}

function resizeGraph(): void {
  if (!graphInstance || !containerRef.value) {
    return
  }
  graphInstance.setSize(containerRef.value.clientWidth || 800, graphHeight())
  scheduleFitGraphView()
}

async function zoomIn(): Promise<void> {
  if (!graphInstance) {
    return
  }
  await graphInstance.zoomBy(GRAPH_ZOOM_STEP)
}

async function zoomOut(): Promise<void> {
  if (!graphInstance) {
    return
  }
  await graphInstance.zoomBy(1 / GRAPH_ZOOM_STEP)
}

async function fitView(): Promise<void> {
  await fitGraphView()
}

async function resetLayout(): Promise<void> {
  if (!graphInstance) {
    return
  }
  await graphInstance.layout()
  await fitGraphView()
}

defineExpose({
  zoomIn,
  zoomOut,
  fitView,
  resetLayout,
})

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
  () => [props.compact, props.fullBleed],
  () => {
    resizeGraph()
  },
)

onUnmounted(() => {
  clearFitViewTimer()
  resizeObserver?.disconnect()
  resizeObserver = null
  graphInstance?.destroy()
  graphInstance = null
})
</script>

<template>
  <div v-if="!graph" class="placeholder">暂无图谱数据</div>
  <div v-else class="paper-graph" :class="{ compact, 'paper-graph--full-bleed': fullBleed }">
    <div ref="containerRef" class="graph-host" :class="{ compact, 'graph-host--full-bleed': fullBleed }" />
    <GraphLegend v-if="compact" :graph="graph" class="paper-graph__legend" />
  </div>
</template>

<style scoped>
.paper-graph {
  position: relative;
  width: 100%;
}

.paper-graph--full-bleed {
  height: 100%;
  min-height: 720px;
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

.graph-host.compact,
.graph-host.graph-host--full-bleed {
  border: none;
}

.graph-host.compact {
  min-height: 320px;
  border-radius: var(--radius-xl);
}

.graph-host.graph-host--full-bleed {
  height: 100%;
  min-height: 720px;
  border-radius: 0;
}

.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}
</style>
