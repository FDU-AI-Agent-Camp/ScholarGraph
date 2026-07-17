<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, toRef, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import PaperMetadataCard from '@/components/papers/PaperMetadataCard.vue'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import BadgeStatus from '@/components/ui/BadgeStatus.vue'
import TagCitation from '@/components/ui/TagCitation.vue'
import { usePaperDetailQa } from '@/composables/usePaperDetailQa'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'
import { resolveClassifyWarningMessages } from '@/utils/classifyWarnings'
import { resolveExtractWarningDisplays } from '@/utils/extractWarnings'
import { formatDetailTime } from '@/utils/formatDetailTime'
import { confirmAndDeletePaper, PAPER_DELETE_COPY } from '@/utils/paperDelete'
import {
  chunkCitationPreview,
  chunkPreviewPlaceholderTooltip,
  citationDisplayId,
  citationKey,
  isChunkPreviewDegraded,
} from '@/utils/qaCitations'
import { isGraphInteractiveStatus, isPreviewAvailableStatus } from '@/utils/paperStatus'

const PaperGraph = defineAsyncComponent(() => import('@/components/graph/PaperGraph.vue'))

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const paperStore = usePaperStore()

const graphLoading = ref(false)
const deleting = ref(false)

/** Capability gates — graph/QA use interactive+preview; Badge uses raw status. */
const isPreview = () => {
  const paper = paperStore.currentPaper
  if (!paper) {
    return false
  }
  return isPreviewAvailableStatus(paper.status, Boolean(paper.preview_available))
}

const isInteractive = () => {
  const status = paperStore.currentPaper?.status
  if (!status) {
    return false
  }
  return isGraphInteractiveStatus(status) || isPreview()
}

const {
  question,
  answer,
  streaming,
  citations,
  qaStreamWarningMessage,
  highlightNodeId,
  resetQaSession,
  ask,
  stopStream,
  focusCitation,
  onGraphNodeClick,
} = usePaperDetailQa(toRef(props, 'paperId'), isInteractive)

const extractWarningDisplays = computed(() => resolveExtractWarningDisplays(paperStore.currentPaper?.extract_warnings))
const classifyWarningMessages = computed(() =>
  resolveClassifyWarningMessages(paperStore.currentPaper?.classify_warnings),
)

function onPipelineTerminalReached(): void {
  void paperStore.fetchDetail(props.paperId)
}

function onPipelineReextracted(): void {
  resetQaSession()
  void paperStore.fetchDetail(props.paperId)
}

async function onDeletePaper(): Promise<void> {
  const paper = paperStore.currentPaper
  if (!paper || deleting.value) {
    return
  }
  const ok = await confirmAndDeletePaper(paper.paper_id, {
    onDeleteInFlight: (inFlight) => {
      deleting.value = inFlight
    },
  })
  if (ok) {
    paperStore.clearCurrent()
    await router.push({ name: RouteName.Papers })
  }
}

async function loadGraphIfReady(): Promise<void> {
  if (!isInteractive() || paperStore.currentGraph?.paper_id === props.paperId) {
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
  () => [paperStore.currentPaper?.status, paperStore.currentPaper?.preview_available],
  () => {
    if (isInteractive()) {
      void loadGraphIfReady()
    }
  },
)

function openFullGraph(): void {
  void router.push({
    name: RouteName.PaperGraph,
    params: { paperId: props.paperId },
    query: highlightNodeId.value ? { node: highlightNodeId.value } : {},
  })
}
</script>

<template>
  <div v-loading="paperStore.loading" class="paper-detail">
    <template v-if="paperStore.currentPaper">
      <header class="detail-header">
        <div class="detail-header__toolbar">
          <RouterLink to="/papers" class="detail-header__back">← {{ DETAIL_BASELINE_COPY.backLink }}</RouterLink>
          <div class="detail-header__actions">
            <el-button
              type="danger"
              plain
              size="small"
              data-testid="detail-delete-button"
              :loading="deleting"
              @click="onDeletePaper"
            >
              {{ PAPER_DELETE_COPY.button }}
            </el-button>
            <el-button v-if="isInteractive()" link type="primary" @click="openFullGraph">
              {{ DETAIL_BASELINE_COPY.fullGraph }}
            </el-button>
          </div>
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
            :auto-start="
              Boolean(paperStore.currentPaper?.status) && !isGraphInteractiveStatus(paperStore.currentPaper.status)
            "
            @terminal-reached="onPipelineTerminalReached"
            @reextracted="onPipelineReextracted"
          />

          <section class="detail-qa">
            <h2 class="text-h2 detail-qa__title">{{ DETAIL_BASELINE_COPY.qaSectionTitle }}</h2>
            <el-alert
              v-if="!isInteractive()"
              type="info"
              :title="DETAIL_BASELINE_COPY.notReadyAlert"
              show-icon
              :closable="false"
              class="detail-qa__alert"
            />
            <el-alert
              v-if="isPreview()"
              type="warning"
              :title="DETAIL_BASELINE_COPY.mvpPreviewAlert"
              show-icon
              :closable="false"
              class="detail-qa__alert detail-qa__alert--mvp"
            />
            <el-input
              v-model="question"
              type="textarea"
              :rows="3"
              class="detail-qa__input"
              :disabled="!isInteractive()"
              :placeholder="DETAIL_BASELINE_COPY.qaPlaceholder"
            />
            <el-space class="detail-qa__actions">
              <el-button type="primary" :loading="streaming" :disabled="!isInteractive()" @click="ask">
                提问
              </el-button>
              <el-button v-if="streaming" :disabled="!isInteractive()" @click="stopStream">停止</el-button>
              <el-button :disabled="!isInteractive()" @click="openFullGraph">
                {{ DETAIL_BASELINE_COPY.fullGraph }}
              </el-button>
            </el-space>
            <div
              v-if="(answer || streaming || qaStreamWarningMessage) && isInteractive()"
              class="detail-qa__answer-panel text-body-lg"
            >
              <el-alert
                v-if="qaStreamWarningMessage"
                type="warning"
                :title="qaStreamWarningMessage"
                show-icon
                :closable="false"
                class="detail-qa__stream-warning"
                data-testid="qa-stream-warning"
              />
              <span class="detail-qa__answer-text">{{ answer }}</span>
              <span v-if="streaming" class="detail-qa__cursor" aria-hidden="true">|</span>
            </div>
            <div v-if="citations.length && isInteractive()" class="detail-qa__citations">
              <span class="text-caption detail-qa__citations-label">{{ DETAIL_BASELINE_COPY.citationLabel }}：</span>
              <div class="citations-list">
                <TagCitation
                  v-for="item in citations"
                  :key="citationKey(item)"
                  :label="item.label"
                  :node-id="citationDisplayId(item)"
                  :active="item.type === 'node' && item.node_id === highlightNodeId"
                  :preview="chunkCitationPreview(item) ?? undefined"
                  :preview-placeholder="item.type === 'chunk' && isChunkPreviewDegraded(item.preview_state)"
                  :preview-tooltip="
                    item.type === 'chunk' ? chunkPreviewPlaceholderTooltip(item.preview_state) : undefined
                  "
                  @click="focusCitation(item)"
                />
              </div>
            </div>
          </section>
        </div>

        <aside class="detail-graph">
          <el-alert
            v-if="classifyWarningMessages.length"
            type="warning"
            :title="classifyWarningMessages[0]"
            show-icon
            :closable="false"
            class="detail-graph__classify-warning"
          />
          <el-alert
            v-if="extractWarningDisplays.length"
            type="warning"
            :title="extractWarningDisplays[0]?.message"
            :description="
              extractWarningDisplays[0]?.technicalCode
                ? `技术代码: ${extractWarningDisplays[0].technicalCode}`
                : undefined
            "
            show-icon
            :closable="false"
            class="detail-graph__extract-warning"
          />
          <div class="detail-graph__header">
            <h2 class="text-h2 detail-graph__title">{{ DETAIL_BASELINE_COPY.graphPreviewTitle }}</h2>
            <el-button v-if="isInteractive()" link type="primary" @click="openFullGraph">
              {{ DETAIL_BASELINE_COPY.graphFullscreenLink }}
            </el-button>
          </div>
          <el-alert
            v-if="isPreview()"
            type="warning"
            :title="DETAIL_BASELINE_COPY.mvpGraphAlert"
            show-icon
            :closable="false"
            class="detail-graph__mvp-alert"
          />
          <div v-loading="graphLoading" class="detail-graph__canvas">
            <PaperGraph
              v-if="isInteractive() && paperStore.currentGraph"
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

.detail-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-8);
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

.detail-qa__stream-warning {
  margin-bottom: var(--spacing-12);
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

.detail-graph__classify-warning {
  margin-bottom: var(--spacing-12);
}

.detail-graph__extract-warning {
  margin-bottom: var(--spacing-12);
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
