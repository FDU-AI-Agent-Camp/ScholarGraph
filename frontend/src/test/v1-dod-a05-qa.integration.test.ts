/**
 * V1 DoD A-05 — SSE 问答：流式答案 + citation → 图谱高亮联动。
 */
import { describe, expect, it } from 'vitest'

import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { UnifiedPaperGraph } from '@/api/types'
import { appendUniqueCitation, buildHighlightStateMap, toG6GraphPayload } from '@/utils/paperGraph'
import { citationNodeId } from '@/utils/qaCitations'
import { readFrontendSource } from '@/test/helpers/designTokens'

/** Frames emitted by backend.graph.qa (see tests/api/test_papers_qa_stream.py). */
const BE_QA_SSE_FRAMES = [
  { event: 'message', data: { delta: '核心论点' } },
  { event: 'citation', data: { type: 'node', paper_id: 'hss-001', node_id: 'n1', label: '核心论点' } },
  { event: 'message', data: { delta: '涉及不平等。' } },
  { event: 'done', data: { answer_id: 'ans-hss-001' } },
] as const

describe('V1 DoD A-05 — SSE QA stream + citation graph linkage', () => {
  it('parses BE qa_stream SSE frames (message / citation / done)', () => {
    const parsed = BE_QA_SSE_FRAMES.map((frame) => parseQaStreamEvent(frame.event, JSON.stringify(frame.data)))
    expect(parsed.every((item) => item !== null)).toBe(true)
    expect(parsed[1]?.type).toBe('citation')
    if (parsed[1]?.type === 'citation') {
      expect(parsed[1].data.paper_id).toBe('hss-001')
      expect(citationNodeId(parsed[1].data)).toBe('n1')
    }
    expect(parsed[3]?.type).toBe('done')
  })

  it('chains citation SSE into graph highlight state for detail compact graph', () => {
    const graph = graphFixture.data as UnifiedPaperGraph
    const nodeIds = toG6GraphPayload(graph).nodes.map((node) => node.id)

    const citations = appendUniqueCitation([], {
      type: 'node' as const,
      paper_id: 'hss-001',
      node_id: 'n1',
      label: '核心论点',
    })
    const highlightNodeId = citationNodeId(citations[citations.length - 1]!)
    const states = buildHighlightStateMap(nodeIds, highlightNodeId)

    expect(states.n1).toBe('active')
    expect(states.n2).toEqual([])
  })

  it('DetailView wires streamPaperQa, citations, and highlightNodeId to PaperGraph', () => {
    const detailSrc = readFrontendSource('views/PaperDetailView.vue')
    const qaComposableSrc = readFrontendSource('composables/usePaperDetailQa.ts')
    expect(qaComposableSrc).toContain('streamPaperQa')
    expect(qaComposableSrc).toContain('onCitation')
    expect(detailSrc).toContain('usePaperDetailQa')
    expect(detailSrc).toContain(':highlight-node-id="highlightNodeId"')
    expect(detailSrc).toContain('TagCitation')
  })

  it('qaStream client POSTs to frozen /papers/{id}/qa/stream path', () => {
    const qaSrc = readFrontendSource('api/qaStream.ts')
    expect(qaSrc).toContain('/papers/${paperId}/qa/stream')
    expect(qaSrc).toContain('fetchEventSource')
    expect(qaSrc).toContain("'citation'")
    expect(qaSrc).toContain("'done'")
  })
})
