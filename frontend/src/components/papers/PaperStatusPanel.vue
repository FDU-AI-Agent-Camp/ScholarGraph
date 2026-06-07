<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { usePaperStatus } from '@/composables/usePaperStatus'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import {
  CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
  hasClassifierHeuristicFallback,
  resolveClassifyWarningMessages,
} from '@/utils/classifyWarnings'
import {
  EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
  hasExtractHeuristicFallback,
  resolveExtractWarningMessages,
} from '@/utils/extractWarnings'
import { isFailedStatus } from '@/utils/paperStatus'
import {
  PIPELINE_REFRESH_CAPTION,
  PIPELINE_STEPS,
  resolvePipelineStepStates,
  type PipelineStepVisualState,
} from '@/utils/pipelineSteps'

const props = defineProps<{
  paperId: string
  autoStart?: boolean
}>()

const emit = defineEmits<{
  ready: []
}>()

const { status, polling, start, stop } = usePaperStatus(props.paperId)
const extractFallbackToastShown = ref(false)
const classifyFallbackToastShown = ref(false)

const failedSnapshot = computed(() => {
  const snapshot = status.value
  return snapshot && isFailedStatus(snapshot) ? snapshot : null
})

const stepStates = computed((): PipelineStepVisualState[] => {
  const snapshot = status.value
  if (!snapshot) {
    return PIPELINE_STEPS.map(() => 'pending')
  }
  return resolvePipelineStepStates(snapshot.stage, snapshot.status, failedSnapshot.value?.failed_during)
})

const extractWarningMessages = computed(() => resolveExtractWarningMessages(status.value?.extract_warnings))
const classifyWarningMessages = computed(() => resolveClassifyWarningMessages(status.value?.classify_warnings))

watch(
  () => props.paperId,
  () => {
    extractFallbackToastShown.value = false
    classifyFallbackToastShown.value = false
    if (props.autoStart) {
      start()
    }
  },
  { immediate: true },
)

watch(
  () => status.value?.status,
  (value) => {
    if (value === 'ready') {
      emit('ready')
    }
  },
)

watch(
  () => status.value,
  (snapshot, previous) => {
    if (!snapshot || snapshot.status !== 'ready' || extractFallbackToastShown.value) {
      return
    }
    if (previous?.status === 'ready') {
      return
    }
    if (!hasExtractHeuristicFallback(snapshot.extract_warnings)) {
      return
    }
    extractFallbackToastShown.value = true
    ElMessage.warning(EXTRACT_HEURISTIC_FALLBACK_MESSAGE)
  },
)

watch(
  () => status.value,
  (snapshot, previous) => {
    if (!snapshot || snapshot.status !== 'ready' || classifyFallbackToastShown.value) {
      return
    }
    if (previous?.status === 'ready') {
      return
    }
    if (!hasClassifierHeuristicFallback(snapshot.classify_warnings)) {
      return
    }
    classifyFallbackToastShown.value = true
    ElMessage.warning(CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE)
  },
)
</script>

<template>
  <section v-if="status" class="status-panel">
    <h2 class="text-h2 status-panel__title">{{ DETAIL_BASELINE_COPY.pipelineTitle }}</h2>
    <div class="status-panel__progress">
      <el-progress
        :percentage="status.percent"
        :status="status.status === 'failed' ? 'exception' : undefined"
        :show-text="false"
        :stroke-width="8"
      />
    </div>
    <ol class="status-panel__steps" aria-label="流水线步骤">
      <li
        v-for="(step, index) in PIPELINE_STEPS"
        :key="step.stage"
        class="status-panel__step"
        :class="`status-panel__step--${stepStates[index]}`"
      >
        <span class="status-panel__marker" aria-hidden="true">
          <span v-if="stepStates[index] === 'done'" class="status-panel__check">✓</span>
        </span>
        <span class="status-panel__label">{{ step.label }}</span>
      </li>
    </ol>
    <p v-if="status.message" class="text-body status-panel__message">{{ status.message }}</p>
    <p class="text-caption status-panel__caption">{{ PIPELINE_REFRESH_CAPTION }}</p>
    <el-alert
      v-if="classifyWarningMessages.length"
      type="warning"
      :title="classifyWarningMessages[0]"
      show-icon
      :closable="false"
      class="status-panel__classify-warning"
    />
    <el-alert
      v-if="extractWarningMessages.length"
      type="warning"
      :title="extractWarningMessages[0]"
      show-icon
      :closable="false"
      class="status-panel__extract-warning"
    />
    <el-alert
      v-if="failedSnapshot"
      type="error"
      :title="failedSnapshot.error_code ?? 'PIPELINE_FAILED'"
      :description="failedSnapshot.message"
      show-icon
      :closable="false"
      class="status-panel__failure"
    />
    <p v-if="failedSnapshot?.failed_during" class="text-caption status-panel__failed-during">
      失败阶段：{{ failedSnapshot.failed_during }}
    </p>
    <div class="status-panel__controls">
      <el-button v-if="!polling" size="small" @click="start">
        {{ DETAIL_BASELINE_COPY.resumeRefresh }}
      </el-button>
      <el-button v-else size="small" @click="stop">
        {{ DETAIL_BASELINE_COPY.pauseRefresh }}
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.status-panel {
  padding: var(--spacing-24);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
}

.status-panel__title {
  margin: 0;
  color: var(--color-text-primary);
}

.status-panel__progress {
  margin-top: var(--spacing-16);
}

.status-panel__progress :deep(.el-progress-bar__outer) {
  background: var(--color-primary-light);
}

.status-panel__progress :deep(.el-progress-bar__inner) {
  background: var(--color-primary);
}

.status-panel__steps {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-12);
  margin: var(--spacing-16) 0 0;
  padding: 0;
  list-style: none;
}

.status-panel__step {
  display: flex;
  align-items: center;
  gap: var(--spacing-12);
}

.status-panel__marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  border-radius: var(--radius-full);
  border: 2px solid var(--color-border-strong);
  background: var(--color-bg-surface);
  flex-shrink: 0;
}

.status-panel__step--active .status-panel__marker {
  border-color: var(--color-primary);
  background: var(--color-primary);
  animation: status-step-pulse var(--duration-pulse) var(--ease-in-subtle) infinite;
}

.status-panel__step--done .status-panel__marker {
  border-color: var(--color-success);
  background: var(--color-success);
}

.status-panel__step--done .status-panel__check {
  animation: status-step-check-in var(--duration-slow) var(--ease-out-product);
}

.status-panel__step--failed .status-panel__marker {
  border-color: var(--color-error);
  background: var(--color-error);
}

.status-panel__check {
  font-size: var(--text-caption-size);
  font-weight: 700;
  line-height: 1;
  color: var(--color-bg-surface);
  transform: scale(0.85);
}

.status-panel__label {
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  line-height: var(--text-body-leading);
  color: var(--color-text-primary);
}

.status-panel__step--active .status-panel__label {
  font-weight: 500;
  color: var(--color-primary);
}

.status-panel__step--done .status-panel__label {
  color: var(--color-text-secondary);
}

.status-panel__step--failed .status-panel__label {
  color: var(--color-error);
}

.status-panel__message {
  margin: var(--spacing-12) 0 0;
  color: var(--color-text-secondary);
}

.status-panel__caption {
  margin: var(--spacing-8) 0 0;
}

.status-panel__extract-warning {
  margin-top: var(--spacing-12);
}

.status-panel__failure {
  margin-top: var(--spacing-12);
}

.status-panel__failed-during {
  margin: var(--spacing-8) 0 0;
  color: var(--color-text-secondary);
}

.status-panel__controls {
  margin-top: var(--spacing-12);
}

@keyframes status-step-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.45;
  }
}

@keyframes status-step-check-in {
  from {
    opacity: 0;
    transform: scale(0.6);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-panel__step--active .status-panel__marker {
    animation: none;
  }

  .status-panel__step--done .status-panel__check {
    animation: none;
  }
}
</style>
