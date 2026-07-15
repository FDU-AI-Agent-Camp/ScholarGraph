<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { isApiClientError } from '@/api/client'
import * as papersApi from '@/api/papers'
import type { PaperStatus } from '@/api/types'
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
  resolveExtractWarningDisplays,
} from '@/utils/extractWarnings'
import {
  isActivePipelineStatus,
  isFailedStatus,
  isGraphInteractiveStatus,
} from '@/utils/paperStatus'
import { resolvePipelineFailureTitle } from '@/utils/pipelineFailureCopy'
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
  /** @deprecated Prefer terminalReached — kept for callers still listening. */
  ready: []
  terminalReached: [status: PaperStatus]
  reextracted: []
}>()

const { status, polling, start, stop, pollOnce } = usePaperStatus(props.paperId)
const extractFallbackToastShown = ref(false)
const classifyFallbackToastShown = ref(false)
const reextracting = ref(false)

const failedSnapshot = computed(() => {
  const snapshot = status.value
  return snapshot && isFailedStatus(snapshot) ? snapshot : null
})

const canReextract = computed(() => Boolean(status.value))

const stepStates = computed((): PipelineStepVisualState[] => {
  const snapshot = status.value
  if (!snapshot) {
    return PIPELINE_STEPS.map(() => 'pending')
  }
  return resolvePipelineStepStates(snapshot.stage, snapshot.status, failedSnapshot.value?.failed_during)
})

const extractWarningDisplays = computed(() => resolveExtractWarningDisplays(status.value?.extract_warnings))
const classifyWarningMessages = computed(() => resolveClassifyWarningMessages(status.value?.classify_warnings))
const failureAlertTitle = computed(() => resolvePipelineFailureTitle(failedSnapshot.value?.error_code))

async function confirmForceReextract(): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      DETAIL_BASELINE_COPY.forceReextractConfirmMessage,
      DETAIL_BASELINE_COPY.forceReextractConfirmTitle,
      {
        type: 'warning',
        confirmButtonText: DETAIL_BASELINE_COPY.forceReextractConfirmOk,
        cancelButtonText: DETAIL_BASELINE_COPY.forceReextractConfirmCancel,
      },
    )
    return true
  } catch {
    return false
  }
}

async function runReextract(force: boolean): Promise<void> {
  const result = await papersApi.forceReextractPaper(props.paperId, { force })
  status.value = result.data
  emit('reextracted')
  ElMessage.success(DETAIL_BASELINE_COPY.reextractSuccess)
  start()
}

async function onReextractClick(): Promise<void> {
  if (reextracting.value || !status.value) {
    return
  }
  reextracting.value = true
  try {
    const current = status.value.status
    if (isActivePipelineStatus(current)) {
      if (!(await confirmForceReextract())) {
        return
      }
      await runReextract(true)
      return
    }

    try {
      await runReextract(false)
    } catch (error) {
      if (isApiClientError(error) && error.code === 'PAPER_ALREADY_PROCESSING') {
        if (!(await confirmForceReextract())) {
          return
        }
        await runReextract(true)
        return
      }
      ElMessage.error(isApiClientError(error) ? error.message : DETAIL_BASELINE_COPY.reextractFailed)
    }
  } catch (error) {
    ElMessage.error(isApiClientError(error) ? error.message : DETAIL_BASELINE_COPY.reextractFailed)
  } finally {
    reextracting.value = false
    void pollOnce()
  }
}

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
  (value, previous) => {
    if (!value || !isGraphInteractiveStatus(value)) {
      return
    }
    if (previous != null && isGraphInteractiveStatus(previous)) {
      return
    }
    emit('terminalReached', value)
    if (value === 'ready') {
      emit('ready')
    }
  },
)

watch(
  () => status.value,
  (snapshot, previous) => {
    if (!snapshot || !isGraphInteractiveStatus(snapshot.status) || extractFallbackToastShown.value) {
      return
    }
    if (previous != null && isGraphInteractiveStatus(previous.status)) {
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
    if (!snapshot || !isGraphInteractiveStatus(snapshot.status) || classifyFallbackToastShown.value) {
      return
    }
    if (previous != null && isGraphInteractiveStatus(previous.status)) {
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
      v-if="extractWarningDisplays.length"
      type="warning"
      :title="extractWarningDisplays[0]?.message"
      :description="
        extractWarningDisplays[0]?.technicalCode ? `技术代码: ${extractWarningDisplays[0].technicalCode}` : undefined
      "
      show-icon
      :closable="false"
      class="status-panel__extract-warning"
    />
    <el-alert
      v-if="failedSnapshot"
      type="error"
      :title="failureAlertTitle"
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
      <el-button
        v-if="canReextract"
        size="small"
        type="warning"
        plain
        :loading="reextracting"
        data-testid="reextract-button"
        @click="onReextractClick"
      >
        {{ DETAIL_BASELINE_COPY.reextractButton }}
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

.status-panel__classify-warning {
  margin-top: var(--spacing-12);
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
