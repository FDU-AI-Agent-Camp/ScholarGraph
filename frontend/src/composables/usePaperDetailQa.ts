import { ref, type Ref } from 'vue'

import { streamPaperQa } from '@/api/qaStream'
import type { QaStreamCitationData } from '@/api/types'
import { appendUniqueCitation } from '@/utils/qaCitations'
import { sanitizeQaAnswer, sanitizeQaAnswerDelta } from '@/utils/qaAnswerSanitize'
import { resolveQaStreamWarningMessage } from '@/utils/qaStreamWarnings'

/**
 * Paper detail multi-scale QA stream session (SSE deltas + citations).
 */
export function usePaperDetailQa(paperId: Ref<string>, isInteractive: () => boolean) {
  const question = ref('')
  const answer = ref('')
  const streaming = ref(false)
  const citations = ref<QaStreamCitationData[]>([])
  const qaStreamWarningMessage = ref<string | null>(null)
  const highlightNodeId = ref<string | null>(null)
  let abort: AbortController | null = null

  function resetQaSession(): void {
    answer.value = ''
    citations.value = []
    qaStreamWarningMessage.value = null
    highlightNodeId.value = null
  }

  async function ask(): Promise<void> {
    if (!question.value.trim() || !isInteractive()) {
      return
    }
    resetQaSession()
    streaming.value = true
    abort = new AbortController()
    try {
      await streamPaperQa(
        paperId.value,
        question.value.trim(),
        {
          onMessage: (data) => {
            answer.value += sanitizeQaAnswerDelta(data.delta)
          },
          onCitation: (data) => {
            citations.value = appendUniqueCitation(citations.value, data)
            if (data.type === 'node') {
              highlightNodeId.value = data.node_id
            }
          },
          onWarning: (data) => {
            qaStreamWarningMessage.value = resolveQaStreamWarningMessage(data)
          },
          onDone: (data) => {
            if (data.answer) {
              answer.value = sanitizeQaAnswer(data.answer)
            } else {
              answer.value = sanitizeQaAnswer(answer.value)
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
    if (citation.type === 'node') {
      highlightNodeId.value = citation.node_id
    }
  }

  function onGraphNodeClick(nodeId: string): void {
    highlightNodeId.value = nodeId
  }

  return {
    question,
    answer,
    streaming,
    citations,
    qaStreamWarningMessage,
    highlightNodeId,
    resetQaSession,
    ask,
    stopStream,
    focusCitation,
    onGraphNodeClick,
  }
}
