<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { streamPaperQa } from '@/api/qaStream'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { usePaperStore } from '@/stores/paper'

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const paperStore = usePaperStore()
const question = ref('')
const answer = ref('')
const streaming = ref(false)
let abort: AbortController | null = null

onMounted(() => {
  void paperStore.fetchDetail(props.paperId)
})

async function ask() {
  if (!question.value.trim()) return
  answer.value = ''
  streaming.value = true
  abort = new AbortController()
  try {
    await streamPaperQa(
      props.paperId,
      question.value.trim(),
      {
        onMessage: (data) => {
          answer.value += data.delta
        },
        onDone: (data) => {
          if (data.answer) answer.value = data.answer
        },
        onError: (msg) => {
          answer.value = `错误: ${msg}`
        },
      },
      abort.signal,
    )
  } finally {
    streaming.value = false
  }
}

function stopStream() {
  abort?.abort()
  streaming.value = false
}
</script>

<template>
  <div v-loading="paperStore.loading" class="page-card">
    <el-page-header @back="router.push('/papers')">
      <template #content>
        <span>{{ paperStore.currentPaper?.title ?? props.paperId }}</span>
      </template>
    </el-page-header>

    <template v-if="paperStore.currentPaper">
      <el-descriptions :column="2" border class="meta">
        <el-descriptions-item label="paper_id">{{ paperStore.currentPaper.paper_id }}</el-descriptions-item>
        <el-descriptions-item label="status">{{ paperStore.currentPaper.status }}</el-descriptions-item>
        <el-descriptions-item label="paradigm">{{ paperStore.currentPaper.paradigm ?? '—' }}</el-descriptions-item>
        <el-descriptions-item v-if="paperStore.currentPaper.classification" label="classification">
          {{ paperStore.currentPaper.classification.paradigm }}
          ({{ paperStore.currentPaper.classification.confidence }})
        </el-descriptions-item>
      </el-descriptions>

      <PaperStatusPanel
        :paper-id="props.paperId"
        :auto-start="paperStore.currentPaper.status !== 'ready'"
        @ready="paperStore.fetchDetail(props.paperId)"
      />

      <el-divider>多尺度问答（SSE）</el-divider>
      <el-input v-model="question" type="textarea" :rows="3" placeholder="输入问题…" />
      <el-space class="actions">
        <el-button type="primary" :loading="streaming" @click="ask">提问</el-button>
        <el-button v-if="streaming" @click="stopStream">停止</el-button>
        <el-button
          v-if="paperStore.currentPaper.status === 'ready'"
          @click="router.push(`/papers/${props.paperId}/graph`)"
        >
          查看图谱
        </el-button>
      </el-space>
      <el-card v-if="answer" shadow="never" class="answer">{{ answer }}</el-card>
    </template>
  </div>
</template>

<style scoped>
.meta {
  margin-top: 16px;
}
.actions {
  margin-top: 12px;
}
.answer {
  margin-top: 16px;
  white-space: pre-wrap;
}
</style>
