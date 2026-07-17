<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed, ref } from 'vue'

import type { GraphNode } from '@/api/types'
import { GRAPH_BASELINE_COPY, GRAPH_DRAWER_WIDTH_PX } from '@/constants/graphCopy'
import { getGraphNodeSnippet } from '@/utils/paperGraph'

const props = defineProps<{
  modelValue: boolean
  node: GraphNode | null
}>()

const emit = defineEmits<{
  'update:modelValue': [visible: boolean]
}>()

const copyHint = ref('')

const snippetText = computed(() => getGraphNodeSnippet(props.node) ?? GRAPH_BASELINE_COPY.drawerNoSnippet)
const hasSnippet = computed(() => getGraphNodeSnippet(props.node) !== null)

function closeDrawer(): void {
  emit('update:modelValue', false)
}

async function copyNodeId(): Promise<void> {
  if (!props.node?.id || typeof navigator === 'undefined' || !navigator.clipboard) {
    return
  }
  await navigator.clipboard.writeText(props.node.id)
  copyHint.value = '已复制'
  window.setTimeout(() => {
    copyHint.value = ''
  }, 1500)
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    append-to-body
    :size="`${GRAPH_DRAWER_WIDTH_PX}px`"
    :with-header="false"
    class="graph-node-drawer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <article v-if="node" class="graph-node-drawer__content">
      <h3 class="text-h3 graph-node-drawer__label">{{ node.label }}</h3>

      <dl class="graph-node-drawer__fields">
        <div class="graph-node-drawer__field">
          <dt class="text-caption graph-node-drawer__field-label">{{ GRAPH_BASELINE_COPY.drawerFieldType }}</dt>
          <dd>
            <span class="graph-node-drawer__type-badge text-caption">{{ node.type }}</span>
          </dd>
        </div>

        <div class="graph-node-drawer__field">
          <dt class="text-caption graph-node-drawer__field-label">{{ GRAPH_BASELINE_COPY.drawerFieldNodeId }}</dt>
          <dd class="graph-node-drawer__node-id-row">
            <code class="text-mono graph-node-drawer__node-id">{{ node.id }}</code>
            <button type="button" class="graph-node-drawer__copy" @click="copyNodeId">
              {{ copyHint || GRAPH_BASELINE_COPY.drawerCopyNodeId }}
            </button>
          </dd>
        </div>

        <div class="graph-node-drawer__field">
          <dt class="text-caption graph-node-drawer__field-label">{{ GRAPH_BASELINE_COPY.drawerFieldSnippet }}</dt>
          <dd
            class="text-body graph-node-drawer__snippet"
            :class="{ 'graph-node-drawer__snippet--empty': !hasSnippet }"
          >
            {{ snippetText }}
          </dd>
        </div>
      </dl>

      <button type="button" class="graph-node-drawer__close text-body" @click="closeDrawer">关闭</button>
    </article>
  </el-drawer>
</template>

<style scoped>
.graph-node-drawer :deep(.el-drawer) {
  transition: transform var(--transition-slow);
}

.graph-node-drawer :deep(.el-overlay) {
  transition: opacity var(--transition-slow);
}

.graph-node-drawer__content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-16);
  padding: var(--spacing-4);
}

.graph-node-drawer__label {
  margin: 0;
  color: var(--color-text-primary);
}

.graph-node-drawer__fields {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-16);
  margin: 0;
}

.graph-node-drawer__field {
  margin: 0;
}

.graph-node-drawer__field-label {
  margin: 0 0 var(--spacing-4);
  color: var(--color-text-secondary);
}

.graph-node-drawer__field dd {
  margin: 0;
}

.graph-node-drawer__type-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-4) var(--spacing-8);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
}

.graph-node-drawer__node-id-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-8);
  flex-wrap: wrap;
}

.graph-node-drawer__node-id {
  color: var(--color-text-primary);
  word-break: break-all;
}

.graph-node-drawer__copy {
  margin: 0;
  padding: var(--spacing-4) var(--spacing-8);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  color: var(--color-primary);
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  line-height: var(--text-caption-leading);
  cursor: pointer;
  transition:
    background-color var(--transition-instant),
    border-color var(--transition-instant),
    color var(--transition-instant);
}

.graph-node-drawer__copy:hover {
  border-color: var(--color-primary-muted);
  background: var(--color-bg-subtle);
}

.graph-node-drawer__snippet {
  margin: 0;
  white-space: pre-wrap;
  color: var(--color-text-primary);
}

.graph-node-drawer__snippet--empty {
  color: var(--color-text-muted);
}

.graph-node-drawer__close {
  align-self: flex-start;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  transition: color var(--transition-instant);
}

.graph-node-drawer__close:hover {
  color: var(--color-primary-hover);
}

@media (prefers-reduced-motion: reduce) {
  .graph-node-drawer :deep(.el-drawer),
  .graph-node-drawer :deep(.el-overlay) {
    transition: none;
  }
}
</style>
