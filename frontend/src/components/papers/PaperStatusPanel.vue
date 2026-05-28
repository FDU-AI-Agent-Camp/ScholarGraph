<script setup lang="ts">
import { computed, watch } from 'vue'

import { usePaperStatus } from '@/composables/usePaperStatus'
import { isFailedStatus } from '@/utils/paperStatus'

const props = defineProps<{
  paperId: string
  autoStart?: boolean
}>()

const emit = defineEmits<{
  ready: []
}>()

const { status, polling, start, stop } = usePaperStatus(props.paperId)

const failedSnapshot = computed(() => {
  const snapshot = status.value
  return snapshot && isFailedStatus(snapshot) ? snapshot : null
})

watch(
  () => props.paperId,
  () => {
    if (props.autoStart) start()
  },
  { immediate: true },
)

watch(
  () => status.value?.status,
  (value) => {
    if (value === 'ready') emit('ready')
  },
)
</script>

<template>
  <el-card v-if="status" shadow="never" class="status-card">
    <template #header>流水线进度</template>
    <el-progress :percentage="status.percent" :status="status.status === 'failed' ? 'exception' : undefined" />
    <p><strong>status</strong>: {{ status.status }}</p>
    <p v-if="status.stage"><strong>stage</strong>: {{ status.stage }}</p>
    <el-alert
      v-if="failedSnapshot"
      type="error"
      :title="failedSnapshot.error_code ?? 'PIPELINE_FAILED'"
      :description="failedSnapshot.message"
      show-icon
      :closable="false"
      class="failure-alert"
    />
    <p v-else>{{ status.message }}</p>
    <p v-if="failedSnapshot?.failed_during">
      <strong>failed_during</strong>: {{ failedSnapshot.failed_during }}
    </p>
    <el-button v-if="!polling" size="small" @click="start">重新轮询</el-button>
    <el-button v-else size="small" @click="stop">停止轮询</el-button>
  </el-card>
</template>

<style scoped>
.status-card {
  margin-top: 16px;
}

.failure-alert {
  margin: 12px 0;
}
</style>
