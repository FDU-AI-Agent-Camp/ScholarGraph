<script setup lang="ts">
import { Graph } from '@antv/g6'
import { onMounted, onUnmounted, ref, watch } from 'vue'

import type { UnifiedPaperGraph } from '@/api/types'

const props = defineProps<{
  graph: UnifiedPaperGraph | null
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let graphInstance: Graph | null = null

function renderGraph() {
  if (!containerRef.value || !props.graph) return
  graphInstance?.destroy()
  graphInstance = new Graph({
    container: containerRef.value,
    width: containerRef.value.clientWidth || 800,
    height: 480,
    data: {
      nodes: props.graph.nodes.map((n) => ({ id: n.id, data: { label: n.label, type: n.type, ...n.data } })),
      edges: props.graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        data: { label: e.label, type: e.type },
      })),
    },
    layout: { type: 'grid' },
    node: {
      style: { size: 36, labelText: (d: { data?: { label?: string } }) => d.data?.label ?? '' },
    },
    edge: {
      style: { labelText: (d: { data?: { label?: string } }) => d.data?.label ?? '' },
    },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
  })
  graphInstance.render()
}

onMounted(renderGraph)
watch(() => props.graph, renderGraph)
onUnmounted(() => {
  graphInstance?.destroy()
  graphInstance = null
})
</script>

<template>
  <div v-if="!graph" class="placeholder">暂无图谱数据</div>
  <div v-else ref="containerRef" class="graph-host" />
</template>

<style scoped>
.graph-host,
.placeholder {
  width: 100%;
  min-height: 480px;
  background: #fafafa;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
}
</style>
