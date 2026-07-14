<script setup lang="ts">
import type { components } from '@/api/types'

type LensClashPoint = components['schemas']['LensClashPoint']

defineProps<{
  point: LensClashPoint
}>()
</script>

<template>
  <article class="patrol-point-card patrol-point-card--lens_clash">
    <dl class="patrol-point-card__fields">
      <div class="patrol-point-card__row">
        <dt>Lens A</dt>
        <dd>{{ point.lens_a }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>Lens B</dt>
        <dd>{{ point.lens_b }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>Aspect</dt>
        <dd>{{ point.clash_aspect }}</dd>
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
