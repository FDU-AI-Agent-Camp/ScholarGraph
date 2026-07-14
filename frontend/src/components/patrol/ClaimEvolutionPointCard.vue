<script setup lang="ts">
import type { components } from '@/api/types'

type ClaimEvolutionPoint = components['schemas']['ClaimEvolutionPoint']

defineProps<{
  point: ClaimEvolutionPoint
}>()
</script>

<template>
  <article class="patrol-point-card patrol-point-card--claim_evolution">
    <header class="patrol-point-card__header">
      <span class="patrol-point-card__label">{{ point.research_question }}</span>
      <span v-if="point.evolution_type" class="text-caption patrol-point-card__type">
        {{ point.evolution_type }}
      </span>
    </header>
    <dl class="patrol-point-card__fields">
      <div v-if="point.paper_a_claim" class="patrol-point-card__row">
        <dt>Paper A</dt>
        <dd>{{ point.paper_a_claim }}</dd>
      </div>
      <div v-if="point.paper_b_claim" class="patrol-point-card__row">
        <dt>Paper B</dt>
        <dd>{{ point.paper_b_claim }}</dd>
      </div>
      <div v-if="point.problem_fit_score != null" class="patrol-point-card__row">
        <dt>Fit</dt>
        <dd class="text-mono">{{ point.problem_fit_score }}</dd>
      </div>
      <div v-if="point.evidence_summary" class="patrol-point-card__row">
        <dt>Evidence</dt>
        <dd>{{ point.evidence_summary }}</dd>
      </div>
    </dl>
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
</style>
