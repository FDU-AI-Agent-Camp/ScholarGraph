<script setup lang="ts">
import { ref } from 'vue'

import type { ParadigmClassification } from '@/api/types'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'

const props = defineProps<{
  classification?: ParadigmClassification | null
}>()

const expanded = ref(false)

function confidencePercent(confidence: number): number {
  return Math.round(confidence * 100)
}
</script>

<template>
  <el-collapse v-if="props.classification" class="metadata-card">
    <el-collapse-item :title="DETAIL_BASELINE_COPY.metadataTitle" name="metadata">
      <div class="metadata-card__body">
        <div class="metadata-card__row">
          <span class="text-caption metadata-card__label">范式</span>
          <BadgeParadigm :paradigm="props.classification.paradigm" />
        </div>
        <div class="metadata-card__row">
          <span class="text-caption metadata-card__label">置信度</span>
          <div class="metadata-card__confidence">
            <span class="text-body">{{ confidencePercent(props.classification.confidence) }}%</span>
            <el-progress
              :percentage="confidencePercent(props.classification.confidence)"
              :show-text="false"
              :stroke-width="4"
              class="metadata-card__confidence-bar"
            />
          </div>
        </div>
        <div class="metadata-card__reason">
          <button type="button" class="metadata-card__reason-toggle" @click="expanded = !expanded">
            {{ DETAIL_BASELINE_COPY.showClassificationReason }}
          </button>
          <p v-if="expanded" class="text-body metadata-card__reason-text">{{ props.classification.reason }}</p>
        </div>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<style scoped>
.metadata-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.metadata-card :deep(.el-collapse-item__header) {
  padding: 0 var(--spacing-16);
  font-family: var(--font-sans);
  font-size: var(--text-h3-size);
  font-weight: var(--text-h3-weight);
  line-height: var(--text-h3-leading);
  color: var(--color-text-primary);
  background: var(--color-bg-surface);
  border-bottom: none;
}

.metadata-card :deep(.el-collapse-item__wrap) {
  border-top: 1px solid var(--color-border);
}

.metadata-card :deep(.el-collapse-item__content) {
  padding: var(--spacing-16);
}

.metadata-card__body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-16);
}

.metadata-card__row {
  display: flex;
  align-items: center;
  gap: var(--spacing-12);
}

.metadata-card__label {
  flex-shrink: 0;
  width: 48px;
  color: var(--color-text-secondary);
}

.metadata-card__confidence {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--spacing-12);
  min-width: 0;
}

.metadata-card__confidence-bar {
  flex: 1;
  max-width: 240px;
}

.metadata-card__confidence-bar :deep(.el-progress-bar__outer) {
  background: var(--color-primary-light);
}

.metadata-card__confidence-bar :deep(.el-progress-bar__inner) {
  background: var(--color-primary);
}

.metadata-card__reason-toggle {
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: 500;
  line-height: var(--text-body-leading);
  color: var(--color-primary);
  cursor: pointer;
  transition: color var(--transition-instant);
}

.metadata-card__reason-toggle:hover {
  color: var(--color-primary-hover);
}

.metadata-card__reason-text {
  margin: var(--spacing-8) 0 0;
  color: var(--color-text-secondary);
}
</style>
