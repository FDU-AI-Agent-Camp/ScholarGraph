<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { components } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { isUsablePatrolNodeRef, patrolGraphLinkForNodeRef, patrolNodeRefKey } from '@/utils/patrolViewHelpers'

type MethodOverlapPoint = components['schemas']['MethodOverlapPoint']

const props = defineProps<{
  point: MethodOverlapPoint
}>()

const usableNodeRefs = computed(() => (props.point.node_refs ?? []).filter(isUsablePatrolNodeRef))
</script>

<template>
  <article class="patrol-point-card patrol-point-card--method_overlap">
    <header class="patrol-point-card__header">
      <span class="patrol-point-card__label">{{ point.overlap_label }}</span>
      <span class="text-caption patrol-point-card__type">{{ point.overlap_type }}</span>
    </header>
    <dl class="patrol-point-card__fields">
      <div class="patrol-point-card__row">
        <dt>Paper A</dt>
        <dd>{{ point.paper_a_usage }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>Paper B</dt>
        <dd>{{ point.paper_b_usage }}</dd>
      </div>
      <div v-if="point.dataset_a || point.dataset_b" class="patrol-point-card__row">
        <dt>Dataset</dt>
        <dd>{{ [point.dataset_a, point.dataset_b].filter(Boolean).join(' · ') }}</dd>
      </div>
      <div v-if="point.overlap_score != null" class="patrol-point-card__row">
        <dt>Score</dt>
        <dd class="text-mono">{{ point.overlap_score }}</dd>
      </div>
      <div v-if="point.match_type" class="patrol-point-card__row">
        <dt>Match</dt>
        <dd>{{ point.match_type }}</dd>
      </div>
      <div v-if="point.evidence_summary" class="patrol-point-card__row">
        <dt>Evidence</dt>
        <dd>{{ point.evidence_summary }}</dd>
      </div>
    </dl>
    <div v-if="usableNodeRefs.length" class="patrol-point-card__node-refs">
      <RouterLink
        v-for="nodeRef in usableNodeRefs"
        :key="patrolNodeRefKey(nodeRef)"
        :to="patrolGraphLinkForNodeRef(nodeRef)"
        class="patrol-point-node-ref text-body"
        data-testid="patrol-point-node-ref"
      >
        <span class="patrol-point-node-ref__label">{{ nodeRef.label || nodeRef.node_id }}</span>
        <span class="text-mono patrol-point-node-ref__meta"> ({{ nodeRef.paper_id }} · {{ nodeRef.node_id }}) </span>
        <span class="patrol-point-node-ref__action">{{ PATROL_BASELINE_COPY.nodeRefGraphLink }}</span>
      </RouterLink>
    </div>
  </article>
</template>

<style scoped>
.patrol-point-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-12);
  padding: var(--spacing-16);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-subtle);
}

.patrol-point-card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--spacing-8);
}

.patrol-point-card__label {
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: 600;
  color: var(--color-text-primary);
}

.patrol-point-card__type {
  color: var(--color-text-secondary);
}

.patrol-point-card__fields {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.patrol-point-card__row {
  display: grid;
  grid-template-columns: 5.5rem minmax(0, 1fr);
  gap: var(--spacing-8);
}

.patrol-point-card__row dt {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-caption-size);
}

.patrol-point-card__row dd {
  margin: 0;
  color: var(--color-text-primary);
  white-space: pre-wrap;
}

.patrol-point-card__node-refs {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

.patrol-point-node-ref {
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
}

.patrol-point-node-ref__meta {
  color: var(--color-text-secondary);
}

.patrol-point-node-ref__action {
  margin-left: auto;
  color: var(--color-primary);
  font-size: var(--text-caption-size);
}
</style>
