<script setup lang="ts">
import type { PatrolMode } from '@/api/types'

defineProps<{
  variant: PatrolMode
  title: string
  insightId?: string
  summary?: string
}>()
</script>

<template>
  <article class="insight-card" :class="`insight-card--${variant}`">
    <header class="insight-card__header">
      <h3 class="insight-card__title">{{ title }}</h3>
      <span v-if="insightId" class="insight-card__id">{{ insightId }}</span>
    </header>
    <p v-if="summary" class="insight-card__summary">{{ summary }}</p>
    <div v-if="$slots.default" class="insight-card__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="insight-card__footer">
      <slot name="footer" />
    </footer>
  </article>
</template>

<style scoped>
.insight-card {
  box-sizing: border-box;
  padding: var(--spacing-24);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
}

.insight-card--lens_clash {
  border-left: 4px solid #ca8a04;
}

.insight-card--contradiction {
  border-left: 4px solid var(--color-error);
}

.insight-card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--spacing-8);
  margin-bottom: var(--spacing-12);
}

.insight-card__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-h3-size);
  font-weight: var(--text-h3-weight);
  line-height: var(--text-h3-leading);
  color: var(--color-text-primary);
}

.insight-card__id {
  font-family: var(--font-mono);
  font-size: var(--text-mono-size);
  line-height: var(--text-mono-leading);
  color: var(--color-text-secondary);
}

.insight-card__summary {
  margin: 0;
  white-space: pre-wrap;
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: var(--text-body-weight);
  line-height: var(--text-body-leading);
  color: var(--color-text-primary);
}

.insight-card__body {
  margin-top: var(--spacing-16);
}

.insight-card__footer {
  margin-top: var(--spacing-16);
}
</style>
