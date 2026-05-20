<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import PaperGraph from '@/components/graph/PaperGraph.vue'
import { usePaperStore } from '@/stores/paper'

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const paperStore = usePaperStore()

onMounted(async () => {
  await paperStore.fetchGraph(props.paperId)
})
</script>

<template>
  <div class="page-card">
    <el-page-header @back="router.push(`/papers/${paperId}`)">
      <template #content>逻辑图谱 · {{ paperId }}</template>
    </el-page-header>
    <PaperGraph :graph="paperStore.currentGraph" />
  </div>
</template>
