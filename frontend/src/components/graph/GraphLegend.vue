<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed } from 'vue'

import type { UnifiedPaperGraph } from '@/api/types'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { listGraphLegendEntries } from '@/utils/paperGraph'

const props = defineProps<{
  graph: UnifiedPaperGraph
}>()

const entries = computed(() => listGraphLegendEntries(props.graph))
</script>

<template>
  <div class="graph-legend" aria-label="图谱节点类型图例">
    <p class="text-caption graph-legend__title">{{ GRAPH_BASELINE_COPY.legendTitle }}</p>
    <ul class="graph-legend__list">
      <li v-for="entry in entries" :key="entry.type" class="graph-legend__item">
        <span class="graph-legend__swatch" :style="{ backgroundColor: entry.color }" aria-hidden="true" />
        <span class="text-caption graph-legend__label">{{ entry.label }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.graph-legend {
  padding: var(--spacing-12);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
}

.graph-legend__title {
  margin: 0 0 var(--spacing-8);
  color: var(--color-text-secondary);
}

.graph-legend__list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
  margin: 0;
  padding: 0;
  list-style: none;
}

.graph-legend__item {
  display: flex;
  align-items: center;
  gap: var(--spacing-8);
}

.graph-legend__swatch {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.graph-legend__label {
  color: var(--color-text-primary);
}
</style>
