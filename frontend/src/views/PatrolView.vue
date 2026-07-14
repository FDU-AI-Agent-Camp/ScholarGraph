<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { isApiClientError } from '@/api/client'
import * as patrolApi from '@/api/patrol'
import type { PatrolMode, PatrolReport } from '@/api/types'
import PatrolStructuredPoints from '@/components/patrol/PatrolStructuredPoints.vue'
import InsightCard from '@/components/ui/InsightCard.vue'
import InsufficientDataInsightCard from '@/components/ui/InsufficientDataInsightCard.vue'
import { usePatrolHealPoll } from '@/composables/usePatrolHealPoll'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'
import { getUnknownErrorMessage } from '@/utils/errors'
import {
  degradationBannerDescription,
  degradationBannerTitle,
  evidencePlaceholderMessage,
  extractReportDegradation,
} from '@/utils/patrolDegradation'
import {
  buildPatrolPaperIds,
  resolvePatrolApiError,
  validatePatrolSelection,
  type PatrolErrorPresentation,
} from '@/utils/patrolForm'
import { isInsufficientDataInsight } from '@/utils/patrolInsufficientData'
import {
  PATROL_MODE_OPTIONS,
  patrolGraphLinkForNodeRef,
  patrolInsightKey,
  patrolModeLabel,
  patrolNodeRefKey,
} from '@/utils/patrolViewHelpers'

const router = useRouter()
const paperStore = usePaperStore()

const paperIdA = ref('hss-001')
const paperIdB = ref('hss-002')
const mode = ref<PatrolMode>('lens_clash')
const loading = ref(false)
const report = ref<PatrolReport | null>(null)
const lastPaperIds = ref<[string, string] | null>(null)
const validationError = ref<string | null>(null)
const apiError = ref<PatrolErrorPresentation | null>(null)

const { healing, scheduleHealPoll, stopHealPoll } = usePatrolHealPoll({
  report,
  paperIds: lastPaperIds,
  mode,
  runPatrol: async (paperIds, patrolMode) => {
    const res = await patrolApi.runPatrol(paperIds, { mode: patrolMode })
    return res.data
  },
})

const degradationProfile = computed(() => (report.value ? extractReportDegradation(report.value) : null))
const paperOptions = computed(() => paperStore.items)
const runButtonLabel = computed(() =>
  loading.value ? PATROL_BASELINE_COPY.runButtonLoading : PATROL_BASELINE_COPY.runButton,
)
/** Alias kept for demo-path / Phase 7 source gates that assert `graphLinkForNodeRef`. */
const graphLinkForNodeRef = patrolGraphLinkForNodeRef

onMounted(() => {
  void paperStore.fetchList().catch(() => undefined)
})

function clearErrors(): void {
  validationError.value = null
  apiError.value = null
}

function resetPaperSelection(): void {
  paperIdA.value = ''
  paperIdB.value = ''
  report.value = null
  lastPaperIds.value = null
  stopHealPoll()
  clearErrors()
}

function onErrorCta(): void {
  if (apiError.value?.ctaKind === 'papers') {
    void router.push({ name: RouteName.Papers })
    return
  }
  if (apiError.value?.ctaKind === 'reset-selection') {
    resetPaperSelection()
  }
}

async function run(): Promise<void> {
  const validation = validatePatrolSelection(paperIdA.value, paperIdB.value)
  validationError.value = validation
  if (validation) {
    report.value = null
    lastPaperIds.value = null
    stopHealPoll()
    apiError.value = null
    return
  }

  loading.value = true
  clearErrors()
  report.value = null
  stopHealPoll()
  const [firstId, secondId] = buildPatrolPaperIds(paperIdA.value, paperIdB.value)
  lastPaperIds.value = [firstId, secondId]

  try {
    const res = await patrolApi.runPatrol([firstId, secondId], { mode: mode.value })
    report.value = res.data
    scheduleHealPoll()
  } catch (error: unknown) {
    if (isApiClientError(error)) {
      apiError.value = resolvePatrolApiError(error.code, error.message)
    } else {
      apiError.value = { title: getUnknownErrorMessage(error) }
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="patrol-view">
    <header class="patrol-view__header">
      <h1 class="text-h1 patrol-view__title">{{ PATROL_BASELINE_COPY.pageTitle }}</h1>
      <p class="text-body patrol-view__subtitle">{{ PATROL_BASELINE_COPY.subtitle }}</p>
    </header>

    <section class="patrol-view__config page-card">
      <h2 class="text-h2 patrol-view__config-title">{{ PATROL_BASELINE_COPY.configTitle }}</h2>

      <div class="patrol-view__paper-grid">
        <label class="patrol-view__field">
          <span class="text-caption patrol-view__field-label">{{ PATROL_BASELINE_COPY.paperLabelA }}</span>
          <el-select
            v-model="paperIdA"
            class="patrol-view__select"
            filterable
            allow-create
            default-first-option
            :placeholder="PATROL_BASELINE_COPY.paperPlaceholder"
          >
            <el-option
              v-for="paper in paperOptions"
              :key="paper.paper_id"
              :label="`${paper.title} (${paper.paper_id})`"
              :value="paper.paper_id"
            />
          </el-select>
        </label>

        <label class="patrol-view__field">
          <span class="text-caption patrol-view__field-label">{{ PATROL_BASELINE_COPY.paperLabelB }}</span>
          <el-select
            v-model="paperIdB"
            class="patrol-view__select"
            filterable
            allow-create
            default-first-option
            :placeholder="PATROL_BASELINE_COPY.paperPlaceholder"
          >
            <el-option
              v-for="paper in paperOptions"
              :key="`${paper.paper_id}-b`"
              :label="`${paper.title} (${paper.paper_id})`"
              :value="paper.paper_id"
            />
          </el-select>
        </label>
      </div>

      <div class="patrol-view__mode">
        <span class="text-caption patrol-view__field-label">{{ PATROL_BASELINE_COPY.modeLabel }}</span>
        <div class="patrol-mode-segment" role="tablist" aria-label="巡检模式">
          <button
            v-for="option in PATROL_MODE_OPTIONS"
            :key="option.value"
            type="button"
            role="tab"
            class="patrol-mode-segment__item"
            :class="{ 'patrol-mode-segment__item--active': mode === option.value }"
            :aria-selected="mode === option.value ? 'true' : 'false'"
            @click="mode = option.value"
          >
            <span class="patrol-mode-segment__label">{{ option.label }}</span>
            <span class="text-caption patrol-mode-segment__caption">{{ option.caption }}</span>
          </button>
        </div>
      </div>

      <el-button type="primary" class="patrol-view__run" :loading="loading" @click="run">
        {{ runButtonLabel }}
      </el-button>

      <details class="patrol-view__hint">
        <summary class="text-caption patrol-view__hint-summary">{{ PATROL_BASELINE_COPY.hintSummary }}</summary>
        <p class="text-caption patrol-view__hint-body">
          {{ PATROL_BASELINE_COPY.hintBody }}
          <code class="text-mono patrol-view__hint-code">{{ PATROL_BASELINE_COPY.hintCommand }}</code>
        </p>
      </details>
    </section>

    <el-alert
      v-if="validationError"
      type="warning"
      :title="validationError"
      show-icon
      :closable="false"
      class="patrol-view__alert"
    />

    <div v-if="apiError" class="patrol-view__error-panel">
      <el-alert type="error" :title="apiError.title" :description="apiError.description" show-icon :closable="false" />
      <el-button v-if="apiError.ctaLabel" type="primary" class="patrol-view__error-cta" @click="onErrorCta">
        {{ apiError.ctaLabel }}
      </el-button>
    </div>

    <section v-if="report" class="patrol-view__report">
      <div class="patrol-view__report-summary">
        <span class="patrol-view__mode-badge text-caption">{{ patrolModeLabel(report.mode) }}</span>
        <span class="text-mono patrol-view__report-time">{{ report.generated_at }}</span>
        <span class="text-mono patrol-view__report-ids">{{ report.paper_ids.join(' · ') }}</span>
      </div>

      <h2 class="text-h2 patrol-view__report-title">{{ PATROL_BASELINE_COPY.reportTitle }}</h2>

      <el-alert
        v-if="degradationProfile"
        type="warning"
        :title="degradationBannerTitle(degradationProfile)"
        :description="degradationBannerDescription(degradationProfile)"
        show-icon
        :closable="false"
        class="patrol-view__alert patrol-view__degradation-banner"
      />
      <p v-if="healing" class="text-caption patrol-view__healing-hint">
        {{ PATROL_BASELINE_COPY.degradationHealingHint }}
      </p>

      <div class="patrol-view__insights">
        <template v-for="item in report.insights" :key="patrolInsightKey(item)">
          <InsufficientDataInsightCard
            v-if="isInsufficientDataInsight(item)"
            :variant="report.mode"
            :title="item.title"
            :insight-id="item.insight_id"
            :summary="item.summary"
            :exclusion-logic="item.exclusion_logic"
          />
          <InsightCard
            v-else
            :variant="report.mode"
            :title="item.title"
            :insight-id="item.insight_id"
            :summary="item.summary"
          >
            <div
              v-if="item.is_degraded || item.degradation_profile"
              class="patrol-view__evidence-placeholder text-caption"
            >
              {{ evidencePlaceholderMessage() }}
            </div>
            <PatrolStructuredPoints v-if="item.structured_points?.length" :points="item.structured_points" />
            <div v-if="item.node_refs.length" class="patrol-view__node-refs">
              <RouterLink
                v-for="nodeRef in item.node_refs"
                :key="patrolNodeRefKey(nodeRef)"
                :to="graphLinkForNodeRef(nodeRef)"
                class="patrol-node-ref text-body"
              >
                <span class="patrol-node-ref__label">{{ nodeRef.label }}</span>
                <span class="text-mono patrol-node-ref__meta">({{ nodeRef.paper_id }} · {{ nodeRef.node_id }})</span>
                <span class="patrol-node-ref__action">{{ PATROL_BASELINE_COPY.nodeRefGraphLink }}</span>
              </RouterLink>
            </div>
          </InsightCard>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.patrol-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-24);
  max-width: var(--content-max-width);
}

.patrol-view__header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.patrol-view__title {
  margin: 0;
  color: var(--color-text-primary);
}

.patrol-view__subtitle {
  margin: 0;
  color: var(--color-text-secondary);
}

.patrol-view__config {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-24);
  padding: var(--spacing-24);
}

.patrol-view__config-title {
  margin: 0;
  color: var(--color-text-primary);
}

.patrol-view__paper-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-16);
}

.patrol-view__field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.patrol-view__field-label {
  color: var(--color-text-secondary);
}

.patrol-view__select {
  width: 100%;
}

.patrol-view__mode {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.patrol-mode-segment {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-8);
  padding: var(--spacing-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-subtle);
}

.patrol-mode-segment__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--spacing-4);
  margin: 0;
  padding: var(--spacing-12) var(--spacing-16);
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  text-align: left;
  cursor: pointer;
  transition:
    background-color var(--transition-instant),
    color var(--transition-instant);
}

.patrol-mode-segment__item:hover:not(.patrol-mode-segment__item--active) {
  background: var(--color-bg-surface);
}

.patrol-mode-segment__item--active {
  background: var(--color-primary);
  color: #ffffff;
}

.patrol-mode-segment__item--active .patrol-mode-segment__caption {
  color: rgb(255 255 255 / 0.82);
}

.patrol-mode-segment__label {
  font-size: var(--text-body-size);
  font-weight: 600;
  line-height: var(--text-body-leading);
}

.patrol-mode-segment__caption {
  color: var(--color-text-secondary);
}

.patrol-view__run {
  align-self: flex-start;
  min-width: 160px;
}

.patrol-view__hint {
  margin: 0;
  padding: var(--spacing-12) var(--spacing-16);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-subtle);
}

.patrol-view__hint-summary {
  cursor: pointer;
  color: var(--color-text-secondary);
}

.patrol-view__hint-body {
  margin: var(--spacing-8) 0 0;
  color: var(--color-text-secondary);
}

.patrol-view__hint-code {
  display: inline-block;
  margin-top: var(--spacing-4);
  color: var(--color-text-primary);
}

.patrol-view__alert {
  margin: 0;
}

.patrol-view__error-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--spacing-12);
}

.patrol-view__error-cta {
  min-width: 160px;
}

.patrol-view__report {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-16);
}

.patrol-view__report-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-12);
  padding: var(--spacing-12) var(--spacing-16);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

.patrol-view__mode-badge {
  padding: var(--spacing-4) var(--spacing-8);
  border-radius: var(--radius-md);
  background: var(--color-primary-light);
  color: var(--color-primary-hover);
}

.patrol-view__report-time,
.patrol-view__report-ids {
  color: var(--color-text-secondary);
}

.patrol-view__report-title {
  margin: 0;
  color: var(--color-text-primary);
}

.patrol-view__healing-hint {
  margin: 0;
  color: var(--color-text-secondary);
}

.patrol-view__evidence-placeholder {
  margin-bottom: var(--spacing-12);
  padding: var(--spacing-12);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-warning, #ca8a04) 8%, transparent);
  color: var(--color-text-secondary);
}

.patrol-view__insights {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-16);
}

.patrol-view__node-refs {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.patrol-node-ref {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-8);
  padding: var(--spacing-8) var(--spacing-12);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-canvas);
  color: var(--color-text-primary);
  text-decoration: none;
  transition:
    border-color var(--transition-instant),
    background-color var(--transition-instant);
}

.patrol-node-ref:hover {
  border-color: var(--color-primary-muted);
  background: var(--color-bg-subtle);
}

.patrol-node-ref__meta {
  color: var(--color-text-secondary);
}

.patrol-node-ref__action {
  margin-left: auto;
  color: var(--color-primary);
  font-size: var(--text-caption-size);
  line-height: var(--text-caption-leading);
}

@media (max-width: 768px) {
  .patrol-view__paper-grid,
  .patrol-mode-segment {
    grid-template-columns: 1fr;
  }
}
</style>
