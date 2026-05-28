<script setup lang="ts">
import { ref } from 'vue'

import * as patrolApi from '@/api/patrol'
import type { PatrolInsight, PatrolReport } from '@/api/types'
import { getUnknownErrorMessage } from '@/utils/errors'

const paperIdsText = ref('hss-001,hss-002')
const loading = ref(false)
const report = ref<PatrolReport | null>(null)
const lastError = ref<string | null>(null)

async function run() {
  const ids = paperIdsText.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  if (!ids.length) return
  loading.value = true
  lastError.value = null
  try {
    const res = await patrolApi.runPatrol(ids)
    report.value = res.data
  } catch (error: unknown) {
    lastError.value = getUnknownErrorMessage(error)
  } finally {
    loading.value = false
  }
}

function insightKey(insight: PatrolInsight): string {
  return insight.insight_id
}
</script>

<template>
  <div class="page-card">
    <h2>共同体巡检</h2>
    <p>输入多篇 ready 论文 ID（逗号分隔），调用 POST /patrol。</p>
    <el-input v-model="paperIdsText" placeholder="hss-001,hss-002" />
    <el-button type="primary" :loading="loading" class="run" @click="run">运行巡检</el-button>
    <el-alert v-if="lastError" type="error" :title="lastError" show-icon class="error" />

    <template v-if="report">
      <h3>{{ report.title ?? report.mode ?? '巡检结果' }}</h3>
      <el-collapse>
        <el-collapse-item
          v-for="item in report.insights"
          :key="insightKey(item)"
          :title="item.title"
          :name="item.insight_id"
        >
          <p>{{ item.summary }}</p>
          <el-tag type="warning">{{ item.severity }}</el-tag>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<style scoped>
h2 {
  margin-top: 0;
}
.run {
  margin-top: 12px;
}
.error {
  margin-top: 12px;
}
</style>
