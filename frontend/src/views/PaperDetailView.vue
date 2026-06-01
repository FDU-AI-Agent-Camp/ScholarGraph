<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { streamPaperQa } from '@/api/qaStream'
import type { QaStreamCitationData } from '@/api/types'
import PaperMetadataCard from '@/components/papers/PaperMetadataCard.vue'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import BadgeStatus from '@/components/ui/BadgeStatus.vue'
import TagCitation from '@/components/ui/TagCitation.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'
import { appendUniqueCitation, citationKey } from '@/utils/qaCitations'

const PaperGraph = defineAsyncComponent(() => import('@/components/graph/PaperGraph.vue'))

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const paperStore = usePaperStore()

const question = ref('')
const answer = ref('')
const streaming = ref(false)
const citations = ref<QaStreamCitationData[]>([])
const highlightNodeId = ref<string | null>(null)
const graphLoading = ref(false)
let abort: AbortController | null = null

const isReady = () => paperStore.currentPaper?.status === 'ready'

function formatDetailTime(iso: string | undefined): string {
  if (!iso) {
    return '—'
  }
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadGraphIfReady(): Promise<void> {
  if (!isReady() || paperStore.currentGraph?.paper_id === props.paperId) {
    return
  }
  graphLoading.value = true
  try {
    await paperStore.fetchGraph(props.paperId)
  } finally {
    graphLoading.value = false
  }
}

onMounted(async () => {
  try {
    await paperStore.fetchDetail(props.paperId)
    await loadGraphIfReady()
  } catch {
    // Store records lastError; template guards on currentPaper.
  }
})

watch(
  () => paperStore.currentPaper?.status,
  (status) => {
    if (status === 'ready') {
      void loadGraphIfReady()
    }
  },
)

async function ask(): Promise<void> {
  if (!question.value.trim() || !isReady()) {
    return
  }
  answer.value = ''
  citations.value = []
  highlightNodeId.value = null
  streaming.value = true
  abort = new AbortController()
  try {
    await streamPaperQa(
      props.paperId,
      question.value.trim(),
      {
        onMessage: (data) => {
          answer.value += data.delta
        },
        onCitation: (data) => {
          citations.value = appendUniqueCitation(citations.value, data)
          highlightNodeId.value = data.node_id
        },
        onDone: (data) => {
          if (data.answer) {
            answer.value = data.answer
          }
        },
        onError: (msg) => {
          answer.value = `错误: ${msg}`
        },
      },
      abort.signal,
    )
  } finally {
    streaming.value = false
  }
}

function stopStream(): void {
  abort?.abort()
  streaming.value = false
}

function focusCitation(citation: QaStreamCitationData): void {
  highlightNodeId.value = citation.node_id
}

function openFullGraph(): void {
  void router.push({
    name: RouteName.PaperGraph,
    params: { paperId: props.paperId },
    query: highlightNodeId.value ? { node: highlightNodeId.value } : {},
  })
}

function onGraphNodeClick(nodeId: string): void {
  highlightNodeId.value = nodeId
}
</script>

<template>
  <div v-loading="paperStore.loading" class="paper-detail">
    <template v-if="paperStore.currentPaper">
      <header class="detail-header">
        <div class="detail-header__toolbar">
          <RouterLink to="/papers" class="detail-header__back">← {{ DETAIL_BASELINE_COPY.backLink }}</RouterLink>
          <el-button v-if="isReady()" link type="primary" @click="openFullGraph">
            {{ DETAIL_BASELINE_COPY.fullGraph }}
          </el-button>
        </div>
        <h1 class="text-h1 detail-header__title">{{ paperStore.currentPaper.title }}</h1>
        <div class="detail-header__meta">
          <span class="text-mono detail-header__paper-id">{{ paperStore.currentPaper.paper_id }}</span>
          <BadgeParadigm :paradigm="paperStore.currentPaper.paradigm" />
          <BadgeStatus :status="paperStore.currentPaper.status" />
          <span class="text-caption detail-header__time">
            {{ formatDetailTime(paperStore.currentPaper.updated_at ?? paperStore.currentPaper.created_at) }}
          </span>
        </div>
      </header>

      <div class="detail-layout">
        <div class="detail-main">
          <PaperMetadataCard :classification="paperStore.currentPaper.classification" />

          <PaperStatusPanel
            :paper-id="props.paperId"
            :auto-start="paperStore.currentPaper.status !== 'ready'"
            @ready="paperStore.fetchDetail(props.paperId)"
          />

          <section class="detail-qa">
            <h2 class="text-h2 detail-qa__title">{{ DETAIL_BASELINE_COPY.qaSectionTitle }}</h2>
            <el-alert
              v-if="!isReady()"
              type="info"
              :title="DETAIL_BASELINE_COPY.notReadyAlert"
              show-icon
              :closable="false"
              class="detail-qa__alert"
            />
            <el-input
              v-model="question"
              type="textarea"
              :rows="3"
              class="detail-qa__input"
              :disabled="!isReady()"
              :placeholder="DETAIL_BASELINE_COPY.qaPlaceholder"
            />
            <el-space class="detail-qa__actions">
              <el-button type="primary" :loading="streaming" :disabled="!isReady()" @click="ask">提问</el-button>
              <el-button v-if="streaming" :disabled="!isReady()" @click="stopStream">停止</el-button>
              <el-button :disabled="!isReady()" @click="openFullGraph">{{ DETAIL_BASELINE_COPY.fullGraph }}</el-button>
            </el-space>
            <div v-if="(answer || streaming) && isReady()" class="detail-qa__answer-panel text-body-lg">
              <span class="detail-qa__answer-text">{{ answer }}</span>
              <span v-if="streaming" class="detail-qa__cursor" aria-hidden="true">|</span>
            </div>
            <div v-if="citations.length && isReady()" class="detail-qa__citations">
              <span class="text-caption detail-qa__citations-label">{{ DETAIL_BASELINE_COPY.citationLabel }}：</span>
              <div class="citations-list">
                <TagCitation
                  v-for="item in citations"
                  :key="citationKey(item)"
                  :label="item.label"
                  :node-id="item.node_id"
                  :active="item.node_id === highlightNodeId"
                  @click="focusCitation(item)"
                />
              </div>
            </div>
          </section>
        </div>

        <aside class="detail-graph">
          <div class="detail-graph__header">
            <h2 class="text-h2 detail-graph__title">{{ DETAIL_BASELINE_COPY.graphPreviewTitle }}</h2>
            <el-button v-if="isReady()" link type="primary" @click="openFullGraph">
              {{ DETAIL_BASELINE_COPY.graphFullscreenLink }}
            </el-button>
          </div>
          <div v-loading="graphLoading" class="detail-graph__canvas">
            <PaperGraph
              v-if="isReady() && paperStore.currentGraph"
              compact
              :graph="paperStore.currentGraph"
              :highlight-node-id="highlightNodeId"
              @node-click="onGraphNodeClick"
            />
            <p v-else class="text-caption detail-graph__placeholder">图谱预览将在论文 ready 后展示</p>
          </div>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.paper-detail {
  min-width: 0;
}

.detail-header {
  padding-bottom: var(--spacing-16);
  border-bottom: 1px solid var(--color-border);
}

.detail-header__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-16);
}

.detail-header__back {
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: 500;
  line-height: var(--text-body-leading);
  color: var(--color-primary);
  text-decoration: none;
  transition: color var(--transition-instant);
}

.detail-header__back:hover {
  color: var(--color-primary-hover);
}

.detail-header__title {
  margin: var(--spacing-12) 0 0;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  color: var(--color-text-primary);
}

.detail-header__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-12);
  margin-top: var(--spacing-12);
}

.detail-header__paper-id {
  color: var(--color-text-secondary);
}

.detail-header__time {
  color: var(--color-text-muted);
}

.detail-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--spacing-24);
  margin-top: var(--spacing-24);
}

.detail-main {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-24);
  min-width: 0;
}

.detail-qa__title {
  margin: 0 0 var(--spacing-16);
  color: var(--color-text-primary);
}

.detail-qa__alert {
  margin-bottom: var(--spacing-12);
}

.detail-qa__actions {
  margin-top: var(--spacing-12);
}

.detail-qa__input :deep(.el-textarea__inner) {
  min-height: 96px;
}

.detail-qa__answer-panel {
  margin-top: var(--spacing-16);
  padding: var(--spacing-16);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-subtle);
  white-space: pre-wrap;
  color: var(--color-text-primary);
}

.detail-qa__cursor {
  margin-left: 2px;
  color: var(--color-primary);
  animation: detail-qa-cursor-blink var(--duration-blink) step-end infinite;
}

.detail-qa__citations {
  margin-top: var(--spacing-12);
}

.detail-qa__citations-label {
  display: inline-block;
  margin-bottom: var(--spacing-8);
  color: var(--color-text-secondary);
}

.citations-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-8);
}

.detail-graph {
  min-width: 0;
}

.detail-graph__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-12);
  margin-bottom: var(--spacing-12);
}

.detail-graph__title {
  margin: 0;
  color: var(--color-text-primary);
}

.detail-graph__canvas {
  position: relative;
  min-height: 320px;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-bg-canvas);
}

.detail-graph__placeholder {
  margin: 0;
  padding: var(--spacing-48) var(--spacing-16);
  text-align: center;
  color: var(--color-text-muted);
}

@media (min-width: 1024px) and (max-width: 1279px) {
  .detail-layout {
    grid-template-columns: 1fr 1fr;
    align-items: start;
  }
}

@media (min-width: 1280px) {
  .detail-layout {
    grid-template-columns: 45fr 55fr;
    align-items: start;
  }
}

@keyframes detail-qa-cursor-blink {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .detail-qa__cursor {
    animation: none;
  }
}
</style>
