<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import PaperUpload from '@/components/papers/PaperUpload.vue'
import { usePaperStore } from '@/stores/paper'

const router = useRouter()
const paperStore = usePaperStore()

onMounted(() => {
  void paperStore.fetchList()
})

function onUploaded(paperId: string) {
  void router.push({ name: 'paper-detail', params: { paperId } })
}
</script>

<template>
  <div class="page-card">
    <h2>文献库</h2>
    <PaperUpload @uploaded="onUploaded" />
    <el-table v-loading="paperStore.loading" :data="paperStore.items" class="table" stripe>
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column prop="paper_id" label="ID" width="280" />
      <el-table-column prop="paradigm" label="范式" width="90" />
      <el-table-column prop="status" label="状态" width="110" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/papers/${row.paper_id}`)">详情</el-button>
          <el-button
            v-if="row.status === 'ready'"
            link
            type="primary"
            @click="router.push(`/papers/${row.paper_id}/graph`)"
          >
            图谱
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
h2 {
  margin-top: 0;
}
.table {
  margin-top: 24px;
}
</style>
