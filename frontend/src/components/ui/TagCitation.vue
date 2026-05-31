<script setup lang="ts">
defineProps<{
  label: string
  nodeId: string
  active?: boolean
}>()

const emit = defineEmits<{
  click: []
}>()

function onClick(): void {
  emit('click')
}
</script>

<template>
  <button
    type="button"
    class="tag-citation citation-tag"
    :class="{ 'tag-citation--active': active }"
    :aria-pressed="active ? 'true' : 'false'"
    @click="onClick"
  >
    <span class="tag-citation__label">{{ label }}</span>
    <span class="tag-citation__node-id">({{ nodeId }})</span>
  </button>
</template>

<style scoped>
.tag-citation {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-4);
  box-sizing: border-box;
  max-width: 100%;
  margin: 0;
  padding: var(--spacing-4) var(--spacing-12);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-canvas);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  line-height: var(--text-body-leading);
  cursor: pointer;
  transition:
    background-color var(--transition-instant),
    border-color var(--transition-instant),
    color var(--transition-instant);
}

.tag-citation:hover {
  border-color: var(--color-primary-muted);
  background: var(--color-bg-subtle);
}

.tag-citation--active {
  border-color: var(--color-citation-active);
  background: var(--color-citation-active-bg);
  color: var(--color-citation-active-text);
  transition:
    background-color var(--transition-fast),
    border-color var(--transition-fast),
    color var(--transition-fast);
}

.tag-citation--active:hover {
  border-color: var(--color-citation-active);
  background: var(--color-citation-active-bg);
}

.tag-citation__node-id {
  font-family: var(--font-mono);
  font-size: var(--text-mono-size);
  line-height: var(--text-mono-leading);
}
</style>
