<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { ApiClientError } from '@/api/client'
import GraphLegend from '@/components/graph/GraphLegend.vue'
import GraphNodeDrawer from '@/components/graph/GraphNodeDrawer.vue'
import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'
import { getUnknownErrorMessage } from '@/utils/errors'
import { findGraphNodeById } from '@/utils/paperGraph'

const PaperGraph = defineAsyncComponent(() => import('@/components/graph/PaperGraph.vue'))

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const route = useRoute()
const paperStore = usePaperStore()

const graphLoading = ref(false)
const graphError = ref<string | null>(null)
const graphErrorCode = ref<string | null>(null)
const highlightNodeId = ref<string | null>(null)
const selectedNodeId = ref<string | null>(null)
const drawerOpen = ref(false)
const graphRef = ref<{
  zoomIn: () => Promise<void>
  zoomOut: () => Promise<void>
  fitView: () => Promise<void>
  resetLayout: () => Promise<void>
} | null>(null)

const graphMeta = computed(() => paperStore.currentGraph)
const paperDetail = computed(() => paperStore.currentPaper)
const nodeCount = computed(() => graphMeta.value?.nodes.length ?? 0)
const edgeCount = computed(() => graphMeta.value?.edges.length ?? 0)
const toolbarDisabled = computed(() => graphLoading.value || Boolean(graphError.value) || !graphMeta.value)
const selectedNode = computed(() => {
  if (!graphMeta.value || !selectedNodeId.value) {
    return null
  }
  return findGraphNodeById(graphMeta.value, selectedNodeId.value) ?? null
})
const isGraphNotReadyError = computed(() => graphErrorCode.value === 'GRAPH_NOT_READY')

function readNodeQueryFromRoute(): string | null {
  const nodeQuery = route.query.node
  return typeof nodeQuery === 'string' && nodeQuery.length > 0 ? nodeQuery : null
}

function syncSelectionFromRoute(openDrawer: boolean): void {
  const nodeId = readNodeQueryFromRoute()
  highlightNodeId.value = nodeId

  if (!nodeId || !graphMeta.value) {
    selectedNodeId.value = null
    if (!nodeId) {
      drawerOpen.value = false
    }
    return
  }

  const node = findGraphNodeById(graphMeta.value, nodeId)
  if (!node) {
    selectedNodeId.value = null
    drawerOpen.value = false
    return
  }

  selectedNodeId.value = node.id
  if (openDrawer) {
    drawerOpen.value = true
  }
}

async function loadGraph(): Promise<void> {
  graphLoading.value = true
  graphError.value = null
  graphErrorCode.value = null
  try {
    if (!paperDetail.value || paperDetail.value.paper_id !== props.paperId) {
      await paperStore.fetchDetail(props.paperId)
    }
    await paperStore.fetchGraph(props.paperId)
    syncSelectionFromRoute(true)
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

function selectNode(nodeId: string, openDrawer = true): void {
  highlightNodeId.value = nodeId
  selectedNodeId.value = nodeId
  if (openDrawer) {
    drawerOpen.value = true
  }
}

function onNodeClick(nodeId: string): void {
  selectNode(nodeId, true)
  void router.replace({
    name: RouteName.PaperGraph,
    params: { paperId: props.paperId },
    query: { node: nodeId },
  })
}

function backToDetail(): void {
  void router.push(`/papers/${props.paperId}`)
}

onMounted(async () => {
  syncSelectionFromRoute(false)
  await loadGraph()
})

watch(
  () => route.query.node,
  () => {
    syncSelectionFromRoute(true)
  },
)
</script>

<template>
  <div v-loading="graphLoading" class="graph-view">
    <el-alert
      class="graph-view__mobile-banner"
      type="info"
      :title="GRAPH_BASELINE_COPY.mobileDesktopBanner"
      show-icon
      :closable="false"
    />
    <header class="graph-view__header">
      <RouterLink :to="`/papers/${paperId}`" class="graph-view__back">← {{ GRAPH_BASELINE_COPY.backLink }}</RouterLink>
      <h1 class="text-h1 graph-view__title">{{ GRAPH_BASELINE_COPY.pageTitle }}</h1>
      <div v-if="graphMeta" class="graph-view__meta">
        <span class="text-mono graph-view__paper-id">{{ paperId }}</span>
        <BadgeParadigm :paradigm="graphMeta.paradigm" />
        <span class="text-caption graph-view__counts">
          {{ GRAPH_BASELINE_COPY.nodeCountLabel }} {{ nodeCount }} · {{ GRAPH_BASELINE_COPY.edgeCountLabel }}
          {{ edgeCount }}
        </span>
      </div>
    </header>

    <section class="graph-view__stage">
      <GraphToolbar
        class="graph-view__toolbar"
        :disabled="toolbarDisabled"
        @zoom-in="graphRef?.zoomIn()"
        @zoom-out="graphRef?.zoomOut()"
        @fit-view="graphRef?.fitView()"
        @reset-layout="graphRef?.resetLayout()"
      />

      <div v-if="graphError" class="graph-view__error-panel">
        <el-alert
          type="error"
          :title="isGraphNotReadyError ? GRAPH_BASELINE_COPY.graphNotReadyTitle : graphError"
          :description="isGraphNotReadyError ? GRAPH_BASELINE_COPY.graphNotReadyDescription : undefined"
          show-icon
          :closable="false"
        />
        <el-button v-if="isGraphNotReadyError" type="primary" class="graph-view__error-cta" @click="backToDetail">
          {{ GRAPH_BASELINE_COPY.graphNotReadyCta }}
        </el-button>
      </div>

      <template v-else-if="graphMeta">
        <PaperGraph
          ref="graphRef"
          :full-bleed="true"
          :graph="graphMeta"
          :highlight-node-id="highlightNodeId"
          @node-click="onNodeClick"
        />
        <GraphLegend :graph="graphMeta" class="graph-view__legend" />
        <GraphNodeDrawer v-model="drawerOpen" :node="selectedNode" />
      </template>
    </section>
  </div>
</template>

<style scoped>
.graph-view {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 56px);
  background: var(--color-bg-canvas);
}

.graph-view__mobile-banner {
  display: none;
  margin: var(--spacing-12) var(--spacing-16) 0;
}

@media (max-width: 767px) {
  .graph-view__mobile-banner {
    display: block;
  }
}

.graph-view__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: var(--spacing-16);
  height: 56px;
  padding: 0 var(--spacing-24);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-surface);
}

.graph-view__back {
  justify-self: start;
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: 500;
  line-height: var(--text-body-leading);
  color: var(--color-primary);
  text-decoration: none;
  transition: color var(--transition-instant);
}

.graph-view__back:hover {
  color: var(--color-primary-hover);
}

.graph-view__title {
  margin: 0;
  justify-self: center;
  color: var(--color-text-primary);
}

.graph-view__meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--spacing-12);
  justify-self: end;
}

.graph-view__paper-id {
  color: var(--color-text-secondary);
}

.graph-view__counts {
  color: var(--color-text-muted);
}

.graph-view__stage {
  position: relative;
  flex: 1;
  min-height: 720px;
  background: var(--color-bg-canvas);
}

.graph-view__toolbar {
  position: absolute;
  top: var(--spacing-16);
  left: 50%;
  z-index: var(--z-graph-toolbar);
  transform: translateX(-50%);
}

.graph-view__legend {
  position: absolute;
  left: var(--spacing-16);
  bottom: var(--spacing-16);
  z-index: var(--z-card);
  max-width: calc(100% - var(--spacing-32));
}

.graph-view__error-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-16);
  min-height: 720px;
  padding: var(--spacing-24);
}

.graph-view__error-cta {
  min-width: 160px;
}
</style>
