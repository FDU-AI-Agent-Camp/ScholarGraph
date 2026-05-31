<script setup lang="ts">
import { ref } from 'vue'

import { isApiClientError } from '@/api/client'
import * as patrolApi from '@/api/patrol'
import type { PatrolInsight, PatrolMode, PatrolReport } from '@/api/types'
import { formatPatrolError, parsePatrolPaperIds, validatePatrolPaperIds } from '@/utils/patrolForm'
import { getUnknownErrorMessage } from '@/utils/errors'

const paperIdsText = ref('hss-001,hss-002')
const mode = ref<PatrolMode>('lens_clash')
const loading = ref(false)
const report = ref<PatrolReport | null>(null)
const lastError = ref<string | null>(null)
const validationError = ref<string | null>(null)

const modeOptions: Array<{ label: string; value: PatrolMode }> = [
  { label: 'Lens Clash（分析视角）', value: 'lens_clash' },
  { label: 'Contradiction（核心论点）', value: 'contradiction' },
]

async function run(): Promise<void> {
  const ids = parsePatrolPaperIds(paperIdsText.value)
  const validation = validatePatrolPaperIds(ids)
  validationError.value = validation
  if (validation) {
    report.value = null
    lastError.value = null
    return
  }

  loading.value = true
  lastError.value = null
  report.value = null
  try {
    const res = await patrolApi.runPatrol(ids, { mode: mode.value })
    report.value = res.data
  } catch (error: unknown) {
    if (isApiClientError(error)) {
      lastError.value = formatPatrolError(error.code, error.message)
    } else {
      lastError.value = getUnknownErrorMessage(error)
    }
  } finally {
    loading.value = false
  }
}

function insightKey(insight: PatrolInsight): string {
  return insight.insight_id
}

function modeLabel(value: PatrolMode): string {
  return modeOptions.find((item) => item.value === value)?.label ?? value
}
</script>

<template>
  <div>
    <h2>共同体巡检</h2>
    <p>输入恰好 2 篇 ready 论文 ID（逗号分隔），调用 POST /patrol。</p>
    <p class="hint">
      本地联调前请在仓库根目录执行：
      <code>uv run python scripts/run_patrol.py --seed-demo-graphs</code>
    </p>

    <el-form label-width="96px" class="form">
      <el-form-item label="paper_ids">
        <el-input v-model="paperIdsText" placeholder="hss-001,hss-002" />
      </el-form-item>
      <el-form-item label="mode">
        <el-radio-group v-model="mode">
          <el-radio v-for="item in modeOptions" :key="item.value" :value="item.value">
            {{ item.label }}
          </el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <el-button type="primary" :loading="loading" class="run" @click="run">运行巡检</el-button>

    <el-alert v-if="validationError" type="warning" :title="validationError" show-icon class="alert" />
    <el-alert v-if="lastError" type="error" :title="lastError" show-icon class="alert" />

    <template v-if="report">
      <el-descriptions :column="2" border class="summary" size="small">
        <el-descriptions-item label="mode">{{ modeLabel(report.mode) }}</el-descriptions-item>
        <el-descriptions-item label="generated_at">{{ report.generated_at }}</el-descriptions-item>
        <el-descriptions-item label="paper_ids" :span="2">
          {{ report.paper_ids.join(', ') }}
        </el-descriptions-item>
      </el-descriptions>

      <el-collapse class="insights">
        <el-collapse-item
          v-for="item in report.insights"
          :key="insightKey(item)"
          :title="item.title"
          :name="item.insight_id"
        >
          <p class="insight-summary">{{ item.summary }}</p>
          <el-table v-if="item.node_refs.length" :data="item.node_refs" size="small" stripe>
            <el-table-column prop="paper_id" label="paper_id" width="120" />
            <el-table-column prop="node_id" label="node_id" width="160" />
            <el-table-column prop="label" label="label" min-width="180" />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<style scoped>
h2 {
  margin-top: 0;
}
.hint {
  color: var(--color-text-secondary);
  font-size: var(--text-caption-size);
  line-height: var(--text-caption-leading);
}
.hint code {
  font-family: var(--font-mono);
}
.form {
  margin-top: 12px;
}
.run {
  margin-top: 4px;
}
.alert {
  margin-top: 12px;
}
.summary {
  margin-top: 16px;
}
.insights {
  margin-top: 16px;
}
.insight-summary {
  margin: 0 0 12px;
  white-space: pre-wrap;
}
</style>
