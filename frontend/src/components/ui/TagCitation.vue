<script setup lang="ts">
defineProps<{
  label: string
  nodeId: string
  active?: boolean
  preview?: string
  previewPlaceholder?: boolean
  previewTooltip?: string
}>()

const emit = defineEmits<{
  click: []
}>()

function onClick(): void {
  emit('click')
}
</script>

<template>
  <div class="tag-citation-wrap">
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
    <p
      v-if="preview"
      class="tag-citation__preview"
      :class="{ 'tag-citation__preview--placeholder': previewPlaceholder }"
      :title="previewTooltip"
    >
      {{ preview }}
    </p>
  </div>
</template>

<style scoped>
.tag-citation-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--spacing-4);
  max-width: 100%;
}

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

.tag-citation__preview {
  margin: 0;
  padding: 0 var(--spacing-4);
  max-width: 100%;
  color: var(--color-text-secondary);
  font-size: var(--text-caption-size, 0.8125rem);
  line-height: 1.4;
  word-break: break-word;
}

.tag-citation__preview--placeholder {
  color: var(--color-warning, #b8860b);
  font-style: italic;
}
</style>
