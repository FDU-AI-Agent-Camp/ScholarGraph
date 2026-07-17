<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed } from 'vue'

import { EMPTY_STATE_PRESETS, type EmptyStateVariant } from '@/components/ui/emptyStatePresets'

const props = defineProps<{
  variant?: EmptyStateVariant
  title?: string
  description?: string
}>()

const resolvedTitle = computed(() => {
  if (props.title) {
    return props.title
  }
  if (props.variant) {
    return EMPTY_STATE_PRESETS[props.variant].title
  }
  return EMPTY_STATE_PRESETS['no-papers'].title
})

const resolvedDescription = computed(() => {
  if (props.description) {
    return props.description
  }
  if (props.variant) {
    return EMPTY_STATE_PRESETS[props.variant].description
  }
  return EMPTY_STATE_PRESETS['no-papers'].description
})
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__illustration" aria-hidden="true">
      <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="24" y="16" width="72" height="88" rx="8" stroke="currentColor" stroke-width="2" />
        <path d="M36 36H84" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        <path d="M36 52H72" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        <path d="M36 68H64" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>
    </div>
    <h3 class="empty-state__title">{{ resolvedTitle }}</h3>
    <p v-if="$slots.body || resolvedDescription" class="empty-state__body">
      <slot name="body">{{ resolvedDescription }}</slot>
    </p>
    <div v-if="$slots.action" class="empty-state__action">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-48) var(--spacing-24);
  text-align: center;
}

.empty-state__illustration {
  width: 120px;
  height: 120px;
  margin-bottom: var(--spacing-24);
  color: var(--color-text-muted);
}

.empty-state__illustration svg {
  display: block;
  width: 100%;
  height: 100%;
}

.empty-state__title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-h3-size);
  font-weight: var(--text-h3-weight);
  line-height: var(--text-h3-leading);
  color: var(--color-text-primary);
}

.empty-state__body {
  margin: var(--spacing-12) 0 0;
  max-width: 360px;
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: var(--text-body-weight);
  line-height: var(--text-body-leading);
  color: var(--color-text-secondary);
}

.empty-state__action {
  margin-top: var(--spacing-24);
}
</style>
