<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { streamPaperQa } from '@/api/qaStream'
import type { QaStreamCitationData } from '@/api/types'
import PaperStatusPanel from '@/components/papers/PaperStatusPanel.vue'
import { RouteName } from '@/router/meta'
import { usePaperStore } from '@/stores/paper'
import { appendUniqueCitation, citationKey } from '@/utils/qaCitations'

const PaperGraph = defineAsyncComponent(() => import('@/components/graph/PaperGraph.vue'))

const props = defineProps<{ paperId: string }>()
const router = useRouter()
const paperStore = usePaperStore()

const question = ref('')
const answer = ref('')
const streaming = ref(false)
const citations = ref<QaStreamCitationData[]>([])
const highlightNodeId = ref<string | null>(null)
const graphLoading = ref(false)
let abort: AbortController | null = null

const isReady = () => paperStore.currentPaper?.status === 'ready'

async function loadGraphIfReady(): Promise<void> {
  if (!isReady() || paperStore.currentGraph?.paper_id === props.paperId) {
    return
  }
  graphLoading.value = true
  try {
    await paperStore.fetchGraph(props.paperId)
  } finally {
    graphLoading.value = false
  }
}

onMounted(async () => {
  await paperStore.fetchDetail(props.paperId)
  await loadGraphIfReady()
})

watch(
  () => paperStore.currentPaper?.status,
  (status) => {
    if (status === 'ready') {
      void loadGraphIfReady()
    }
  },
)

async function ask(): Promise<void> {
  if (!question.value.trim() || !isReady()) {
    return
  }
  answer.value = ''
  citations.value = []
  highlightNodeId.value = null
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
        onCitation: (data) => {
          citations.value = appendUniqueCitation(citations.value, data)
          highlightNodeId.value = data.node_id
        },
        onDone: (data) => {
          if (data.answer) {
            answer.value = data.answer
          }
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

function stopStream(): void {
  abort?.abort()
  streaming.value = false
}

function focusCitation(citation: QaStreamCitationData): void {
  highlightNodeId.value = citation.node_id
}

function openFullGraph(): void {
  void router.push({
    name: RouteName.PaperGraph,
    params: { paperId: props.paperId },
    query: highlightNodeId.value ? { node: highlightNodeId.value } : {},
  })
}

function onGraphNodeClick(nodeId: string): void {
  highlightNodeId.value = nodeId
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
      <el-alert
        v-if="!isReady()"
        type="info"
        title="论文尚未 ready，问答与图谱预览将在流水线完成后可用。"
        show-icon
        :closable="false"
        class="qa-hint"
      />
      <template v-else>
        <el-input v-model="question" type="textarea" :rows="3" placeholder="输入问题…" />
        <el-space class="actions">
          <el-button type="primary" :loading="streaming" @click="ask">提问</el-button>
          <el-button v-if="streaming" @click="stopStream">停止</el-button>
          <el-button @click="openFullGraph"> 全屏图谱 </el-button>
        </el-space>
        <el-card v-if="answer" shadow="never" class="answer">{{ answer }}</el-card>
        <div v-if="citations.length" class="citations">
          <span class="citations-label">引用节点：</span>
          <el-space wrap>
            <el-tag
              v-for="item in citations"
              :key="citationKey(item)"
              :type="item.node_id === highlightNodeId ? 'danger' : 'info'"
              class="citation-tag"
              @click="focusCitation(item)"
            >
              {{ item.label }} ({{ item.node_id }})
            </el-tag>
          </el-space>
        </div>

        <el-divider>逻辑图谱预览</el-divider>
        <div v-loading="graphLoading">
          <PaperGraph
            v-if="paperStore.currentGraph"
            compact
            :graph="paperStore.currentGraph"
            :highlight-node-id="highlightNodeId"
            @node-click="onGraphNodeClick"
          />
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.meta {
  margin-top: 16px;
}
.qa-hint {
  margin-bottom: 12px;
}
.actions {
  margin-top: 12px;
}
.answer {
  margin-top: 16px;
  white-space: pre-wrap;
}
.citations {
  margin-top: 12px;
}
.citations-label {
  display: inline-block;
  margin-bottom: var(--spacing-8);
  color: var(--color-text-secondary);
}
.citation-tag {
  cursor: pointer;
}
</style>
