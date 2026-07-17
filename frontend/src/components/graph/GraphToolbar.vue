<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { FullScreen, RefreshRight, Search, ZoomIn, ZoomOut } from '@element-plus/icons-vue'

import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'

withDefaults(
  defineProps<{
    disabled?: boolean
  }>(),
  {
    disabled: false,
  },
)

const emit = defineEmits<{
  zoomIn: []
  zoomOut: []
  fitView: []
  resetLayout: []
}>()
</script>

<template>
  <div class="graph-toolbar" role="toolbar" aria-label="图谱工具栏">
    <div class="graph-toolbar__actions">
      <button
        type="button"
        class="graph-toolbar__button"
        :disabled="disabled"
        :title="GRAPH_BASELINE_COPY.toolbarZoomIn"
        :aria-label="GRAPH_BASELINE_COPY.toolbarZoomIn"
        @click="emit('zoomIn')"
      >
        <el-icon><ZoomIn /></el-icon>
      </button>
      <button
        type="button"
        class="graph-toolbar__button"
        :disabled="disabled"
        :title="GRAPH_BASELINE_COPY.toolbarZoomOut"
        :aria-label="GRAPH_BASELINE_COPY.toolbarZoomOut"
        @click="emit('zoomOut')"
      >
        <el-icon><ZoomOut /></el-icon>
      </button>
      <button
        type="button"
        class="graph-toolbar__button"
        :disabled="disabled"
        :title="GRAPH_BASELINE_COPY.toolbarFitView"
        :aria-label="GRAPH_BASELINE_COPY.toolbarFitView"
        @click="emit('fitView')"
      >
        <el-icon><FullScreen /></el-icon>
      </button>
      <button
        type="button"
        class="graph-toolbar__button"
        :disabled="disabled"
        :title="GRAPH_BASELINE_COPY.toolbarResetLayout"
        :aria-label="GRAPH_BASELINE_COPY.toolbarResetLayout"
        @click="emit('resetLayout')"
      >
        <el-icon><RefreshRight /></el-icon>
      </button>
    </div>
    <span class="graph-toolbar__divider" aria-hidden="true" />
    <label class="graph-toolbar__search">
      <el-icon class="graph-toolbar__search-icon"><Search /></el-icon>
      <input
        type="search"
        class="graph-toolbar__search-input text-body"
        :placeholder="GRAPH_BASELINE_COPY.toolbarSearchPlaceholder"
        disabled
        aria-disabled="true"
      />
    </label>
  </div>
</template>

<style scoped>
.graph-toolbar {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-12);
  padding: var(--spacing-8) var(--spacing-12);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-md);
}

.graph-toolbar__actions {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-4);
}

.graph-toolbar__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  margin: 0;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    background-color var(--transition-instant),
    border-color var(--transition-instant),
    color var(--transition-instant);
}

.graph-toolbar__button:hover:not(:disabled) {
  border-color: var(--color-border);
  background: var(--color-bg-subtle);
  color: var(--color-primary);
}

.graph-toolbar__button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.graph-toolbar__divider {
  width: 1px;
  height: 24px;
  background: var(--color-border);
}

.graph-toolbar__search {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-8);
  width: 200px;
}

.graph-toolbar__search-icon {
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.graph-toolbar__search-input {
  width: 100%;
  min-width: 0;
  margin: 0;
  padding: var(--spacing-4) 0;
  border: none;
  background: transparent;
  color: var(--color-text-primary);
  outline: none;
}

.graph-toolbar__search-input:disabled {
  cursor: not-allowed;
  color: var(--color-text-muted);
}

.graph-toolbar__search-input::placeholder {
  color: var(--color-text-muted);
}
</style>
