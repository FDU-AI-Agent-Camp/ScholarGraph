<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import type { PaperSummary } from '@/api/types'
import PaperUpload from '@/components/papers/PaperUpload.vue'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import BadgeStatus from '@/components/ui/BadgeStatus.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'

const PAPERS_TITLE = '文献库'
const PAPERS_SUBTITLE = '管理已上传论文，查看解构进度与图谱入口'
const UPLOAD_SECTION_TITLE = '上传论文'
const TABLE_SECTION_TITLE = '全部文献'

const router = useRouter()
const paperStore = usePaperStore()
const uploadSectionRef = ref<HTMLElement | null>(null)

onMounted(() => {
  void paperStore.fetchList()
})

function onUploaded(paperId: string) {
  void router.push({ name: RouteName.PaperDetail, params: { paperId } })
}

function openDetail(row: PaperSummary) {
  void router.push({ name: RouteName.PaperDetail, params: { paperId: row.paper_id } })
}

function openGraph(row: PaperSummary) {
  void router.push({ name: RouteName.PaperGraph, params: { paperId: row.paper_id } })
}

function scrollToUpload() {
  uploadSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function copyPaperId(paperId: string) {
  try {
    await navigator.clipboard.writeText(paperId)
    ElMessage.success('已复制 paper_id')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}
</script>

<template>
  <div class="papers">
    <header class="papers-header">
      <h1 class="text-h1 papers-title">{{ PAPERS_TITLE }}</h1>
      <p class="text-body papers-subtitle">{{ PAPERS_SUBTITLE }}</p>
    </header>

    <section id="papers-upload" ref="uploadSectionRef" class="papers-section">
      <h2 class="text-h2 papers-section-title">{{ UPLOAD_SECTION_TITLE }}</h2>
      <PaperUpload @uploaded="onUploaded" />
    </section>

    <section class="papers-section papers-section--table">
      <h2 class="text-h2 papers-section-title">{{ TABLE_SECTION_TITLE }}</h2>
      <el-table
        v-if="paperStore.items.length > 0"
        v-loading="paperStore.loading"
        :data="paperStore.items"
        class="papers-table"
        stripe
      >
        <el-table-column prop="title" label="标题" min-width="240">
          <template #default="{ row }: { row: PaperSummary }">
            <span class="papers-table__title">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="范式" width="88">
          <template #default="{ row }: { row: PaperSummary }">
            <BadgeParadigm :paradigm="row.paradigm" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }: { row: PaperSummary }">
            <BadgeStatus :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="paper_id" label="paper_id" width="200">
          <template #default="{ row }: { row: PaperSummary }">
            <span class="papers-table__paper-id">
              <span class="papers-table__paper-id-text text-mono">{{ row.paper_id }}</span>
              <button
                type="button"
                class="papers-table__copy"
                aria-label="复制 paper_id"
                @click="copyPaperId(row.paper_id)"
              >
                <el-icon aria-hidden="true"><DocumentCopy /></el-icon>
              </button>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }: { row: PaperSummary }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="row.status === 'ready'" link type="primary" @click="openGraph(row)"> 图谱 </el-button>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-else-if="!paperStore.loading" variant="no-papers" class="papers-empty">
        <template #action>
          <el-button type="primary" plain @click="scrollToUpload">上传 PDF</el-button>
        </template>
      </EmptyState>
    </section>
  </div>
</template>

<style scoped>
.papers-header {
  margin: 0;
}

.papers-title {
  margin: 0;
  color: var(--color-text-primary);
}

.papers-subtitle {
  margin: var(--spacing-8) 0 0;
  color: var(--color-text-secondary);
}

.papers-section {
  margin-top: var(--spacing-32);
}

.papers-section-title {
  margin: 0 0 var(--spacing-16);
  color: var(--color-text-primary);
}

.papers-section--table {
  margin-top: var(--spacing-32);
}

.papers-table {
  width: 100%;
}

.papers-table :deep(.el-table__header-wrapper th.el-table__cell) {
  background: var(--color-bg-page);
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  font-weight: 500;
  line-height: var(--text-caption-leading);
  color: var(--color-text-secondary);
}

.papers-table :deep(.el-table__body td.el-table__cell) {
  padding-top: 0;
  padding-bottom: 0;
}

.papers-table :deep(.el-table__body tr) {
  height: 52px;
}

.papers-table :deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: var(--color-bg-subtle);
}

.papers-table :deep(.el-table__body tr:hover > td.el-table__cell) {
  background: rgb(230 243 243 / 20%);
}

.papers-table__title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  font-weight: 500;
  line-height: var(--text-body-leading);
  color: var(--color-text-primary);
}

.papers-table__paper-id {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-4);
  max-width: 100%;
}

.papers-table__paper-id-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
}

.papers-table__copy {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-4);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition:
    color var(--transition-instant),
    background var(--transition-instant);
}

.papers-table__copy:hover {
  color: var(--color-primary);
  background: var(--color-primary-light);
}

.papers-empty {
  margin-top: var(--spacing-24);
}
</style>
