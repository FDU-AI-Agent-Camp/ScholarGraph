<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed } from 'vue'

import type { PaperStatus } from '@/api/types'

const props = defineProps<{
  status: PaperStatus
}>()

const STATUS_LABELS: Record<PaperStatus, string> = {
  pending: '待开始',
  processing: '解构中',
  indexing: '索引中',
  ready: '已就绪',
  ready_with_warnings: '已就绪（有警告）',
  failed: '失败',
}

const label = computed(() => STATUS_LABELS[props.status])
</script>

<template>
  <span class="badge-status" :class="`badge-status--${status}`">
    <span class="badge-status__dot" aria-hidden="true" />
    <span class="badge-status__label">{{ label }}</span>
  </span>
</template>

<style scoped>
.badge-status {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-8);
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  font-weight: 500;
  line-height: var(--text-caption-leading);
  color: var(--color-text-primary);
  white-space: nowrap;
}

.badge-status__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.badge-status--pending .badge-status__dot {
  background: var(--color-text-muted);
}

.badge-status--processing .badge-status__dot,
.badge-status--indexing .badge-status__dot {
  background: var(--color-info);
  animation: badge-status-pulse var(--duration-pulse) var(--ease-in-subtle) infinite;
}

.badge-status--ready .badge-status__dot {
  background: var(--color-success);
}

.badge-status--ready_with_warnings .badge-status__dot {
  background: var(--color-warning);
}

.badge-status--failed .badge-status__dot {
  background: var(--color-error);
}

@keyframes badge-status-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.45;
  }
}

@media (prefers-reduced-motion: reduce) {
  .badge-status--processing .badge-status__dot,
  .badge-status--indexing .badge-status__dot {
    animation: none;
  }
}
</style>
