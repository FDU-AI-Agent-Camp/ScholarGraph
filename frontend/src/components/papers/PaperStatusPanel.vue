<script setup lang="ts">
import { watch } from 'vue'

import { usePaperStatus } from '@/composables/usePaperStatus'

const props = defineProps<{
  paperId: string
  autoStart?: boolean
}>()

const emit = defineEmits<{
  ready: []
}>()

const { status, polling, start, stop } = usePaperStatus(props.paperId)

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
    <p>{{ status.message }}</p>
    <el-button v-if="!polling" size="small" @click="start">重新轮询</el-button>
    <el-button v-else size="small" @click="stop">停止轮询</el-button>
  </el-card>
</template>

<style scoped>
.status-card {
  margin-top: 16px;
}
</style>
