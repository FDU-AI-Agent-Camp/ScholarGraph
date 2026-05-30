<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiClientError } from '@/api/client'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'
import { getUnknownErrorMessage } from '@/utils/errors'

const PaperGraph = defineAsyncComponent(() => import('@/components/graph/PaperGraph.vue'))

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const route = useRoute()
const paperStore = usePaperStore()

const graphLoading = ref(false)
const graphError = ref<string | null>(null)
const graphErrorCode = ref<string | null>(null)
const highlightNodeId = ref<string | null>(null)

const graphMeta = computed(() => paperStore.currentGraph)

function readHighlightFromRoute(): void {
  const nodeQuery = route.query.node
  highlightNodeId.value = typeof nodeQuery === 'string' && nodeQuery.length > 0 ? nodeQuery : null
}

async function loadGraph(): Promise<void> {
  graphLoading.value = true
  graphError.value = null
  graphErrorCode.value = null
  try {
    await paperStore.fetchGraph(props.paperId)
  } catch (error: unknown) {
    if (error instanceof ApiClientError) {
      graphErrorCode.value = error.code
      graphError.value = error.message
    } else {
      graphError.value = getUnknownErrorMessage(error)
    }
  } finally {
    graphLoading.value = false
  }
}

function onNodeClick(nodeId: string): void {
  highlightNodeId.value = nodeId
  void router.replace({
    name: RouteName.PaperGraph,
    params: { paperId: props.paperId },
    query: { node: nodeId },
  })
}

onMounted(async () => {
  readHighlightFromRoute()
  await loadGraph()
})

watch(
  () => route.query.node,
  () => {
    readHighlightFromRoute()
  },
)
</script>

<template>
  <div v-loading="graphLoading" class="page-card">
    <el-page-header @back="router.push(`/papers/${paperId}`)">
      <template #content>逻辑图谱 · {{ paperId }}</template>
    </el-page-header>

    <el-alert
      v-if="graphError"
      type="error"
      :title="graphError"
      :description="graphErrorCode === 'GRAPH_NOT_READY' ? '论文尚未 ready，请先在详情页等待流水线完成。' : undefined"
      show-icon
      class="graph-error"
    />

    <template v-else-if="graphMeta">
      <el-descriptions :column="3" border class="meta" size="small">
        <el-descriptions-item label="paradigm">{{ graphMeta.paradigm }}</el-descriptions-item>
        <el-descriptions-item label="节点数">{{ graphMeta.nodes.length }}</el-descriptions-item>
        <el-descriptions-item label="边数">{{ graphMeta.edges.length }}</el-descriptions-item>
      </el-descriptions>
      <PaperGraph :graph="graphMeta" :highlight-node-id="highlightNodeId" @node-click="onNodeClick" />
    </template>
  </div>
</template>

<style scoped>
.meta {
  margin: 16px 0;
}
.graph-error {
  margin-top: 16px;
}
</style>
