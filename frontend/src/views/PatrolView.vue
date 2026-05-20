<script setup lang="ts">
import { ref } from 'vue'

import * as patrolApi from '@/api/patrol'
import type { PatrolReport } from '@/api/types'

const paperIdsText = ref('hss-001,hss-002')
const loading = ref(false)
const report = ref<PatrolReport | null>(null)

async function run() {
  const ids = paperIdsText.value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  if (!ids.length) return
  loading.value = true
  try {
    const res = await patrolApi.runPatrol(ids)
    report.value = res.data
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page-card">
    <h2>共同体巡检</h2>
    <p>输入多篇 ready 论文 ID（逗号分隔），调用 POST /patrol。</p>
    <el-input v-model="paperIdsText" placeholder="hss-001,hss-002" />
    <el-button type="primary" :loading="loading" class="run" @click="run">运行巡检</el-button>

    <template v-if="report">
      <h3>{{ report.title }}</h3>
      <el-collapse>
        <el-collapse-item
          v-for="item in report.insights"
          :key="item.insight_id"
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
</style>
