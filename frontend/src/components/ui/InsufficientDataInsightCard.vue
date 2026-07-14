<script setup lang="ts">
import { computed } from 'vue'

import type { PatrolExclusionLogic, PatrolMode } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import {
  exclusionDescription,
  exclusionReasonTitle,
  formatExclusionPhase,
  insufficientDataBadgeLabel,
} from '@/utils/patrolInsufficientData'

const props = defineProps<{
  variant: PatrolMode
  title: string
  insightId?: string
  summary: string
  exclusionLogic?: PatrolExclusionLogic | null
}>()

const badge = insufficientDataBadgeLabel()
const reasonTitle = computed(() => exclusionReasonTitle(props.exclusionLogic?.reason_code))
const body = computed(() => exclusionDescription(props.exclusionLogic, props.summary))
const phase = computed(() => formatExclusionPhase(props.exclusionLogic?.phase))
</script>

<template>
  <article
    class="insufficient-insight-card"
    :class="`insufficient-insight-card--${variant}`"
    data-testid="insufficient-data-insight-card"
  >
    <header class="insufficient-insight-card__header">
      <div class="insufficient-insight-card__title-row">
        <span class="insufficient-insight-card__badge">{{ badge }}</span>
        <h3 class="insufficient-insight-card__title">{{ title }}</h3>
      </div>
      <span v-if="insightId" class="insufficient-insight-card__id">{{ insightId }}</span>
    </header>

    <p class="insufficient-insight-card__reason-title">{{ reasonTitle }}</p>
    <p class="insufficient-insight-card__body">{{ body }}</p>
    <p v-if="phase" class="insufficient-insight-card__phase text-caption">
      {{ PATROL_BASELINE_COPY.insufficientInsightPhaseLabel }}：
      <span class="text-mono">{{ phase }}</span>
    </p>
    <p class="insufficient-insight-card__hint text-caption">
      {{ PATROL_BASELINE_COPY.insufficientInsightHint }}
    </p>
  </article>
</template>

<style scoped>
.insufficient-insight-card {
  box-sizing: border-box;
  padding: var(--spacing-24);
  border: 1px solid color-mix(in srgb, var(--color-citation-preview-placeholder) 35%, var(--color-border));
  border-left: 4px solid var(--color-citation-preview-placeholder);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-citation-preview-placeholder) 8%, var(--color-bg-surface));
  box-shadow: var(--shadow-sm);
}

.insufficient-insight-card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--spacing-8);
  margin-bottom: var(--spacing-12);
}

.insufficient-insight-card__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-8);
}

.insufficient-insight-card__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-citation-preview-placeholder) 18%, transparent);
  color: var(--color-hss-text);
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  font-weight: 600;
  line-height: var(--text-caption-leading);
}

.insufficient-insight-card__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-h3-size);
  font-weight: var(--text-h3-weight);
  line-height: var(--text-h3-leading);
  color: var(--color-text-primary);
}

.insufficient-insight-card__id {
  font-family: var(--font-mono);
  font-size: var(--text-mono-size);
  line-height: var(--text-mono-leading);
  color: var(--color-text-secondary);
}

.insufficient-insight-card__reason-title {
  margin: 0 0 var(--spacing-8);
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: 600;
  line-height: var(--text-body-leading);
  color: var(--color-hss-text);
}

.insufficient-insight-card__body {
  margin: 0;
  white-space: pre-wrap;
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: var(--text-body-weight);
  line-height: var(--text-body-leading);
  color: var(--color-text-primary);
}

.insufficient-insight-card__phase {
  margin: var(--spacing-12) 0 0;
  color: var(--color-text-secondary);
}

.insufficient-insight-card__hint {
  margin: var(--spacing-12) 0 0;
  color: var(--color-text-secondary);
}
</style>
