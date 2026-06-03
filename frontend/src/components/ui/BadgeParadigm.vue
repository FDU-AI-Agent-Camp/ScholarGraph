<script setup lang="ts">
import { computed } from 'vue'

import type { Paradigm } from '@/api/types'

export type ParadigmBadgeVariant = Paradigm | 'unknown'

const props = defineProps<{
  /** HSS / STEM from API; nullish values render as unknown. */
  paradigm?: Paradigm | null | string
}>()

const variant = computed((): ParadigmBadgeVariant => {
  if (props.paradigm === 'HSS' || props.paradigm === 'STEM') {
    return props.paradigm
  }
  return 'unknown'
})

const label = computed(() => {
  if (variant.value === 'HSS') {
    return 'HSS'
  }
  if (variant.value === 'STEM') {
    return 'STEM'
  }
  return '未知'
})
</script>

<template>
  <span class="badge-paradigm" :class="`badge-paradigm--${variant}`">{{ label }}</span>
</template>

<style scoped>
.badge-paradigm {
  display: inline-flex;
  align-items: center;
  box-sizing: border-box;
  padding: 2px var(--spacing-8);
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  font-weight: 500;
  line-height: var(--text-caption-leading);
  white-space: nowrap;
}

.badge-paradigm--HSS {
  background: var(--color-hss-bg);
  color: var(--color-hss-text);
}

.badge-paradigm--STEM {
  background: var(--color-stem-bg);
  color: var(--color-stem-text);
}

.badge-paradigm--unknown {
  background: var(--color-bg-canvas);
  color: var(--color-text-secondary);
}
</style>
