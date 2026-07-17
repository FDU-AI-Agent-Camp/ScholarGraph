/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { ref, type Ref } from 'vue'

import { streamPaperQa } from '@/api/qaStream'
import type { QaStreamCitationData } from '@/api/types'
import { appendUniqueCitation } from '@/utils/qaCitations'
import { sanitizeQaAnswer, QaAnswerDeltaSanitizer } from '@/utils/qaAnswerSanitize'
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
    const deltaSanitizer = new QaAnswerDeltaSanitizer()
    try {
      await streamPaperQa(
        paperId.value,
        question.value.trim(),
        {
          onMessage: (data) => {
            const cleaned = deltaSanitizer.feed(data.delta)
            if (cleaned) {
              answer.value += cleaned
            }
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
            const tail = deltaSanitizer.flush()
            if (tail) {
              answer.value += tail
            }
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
