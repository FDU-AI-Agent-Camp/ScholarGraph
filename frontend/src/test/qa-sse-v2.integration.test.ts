/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * B6 integration: V2 QA SSE fixture ↔ parser ↔ citation helpers ↔ OpenAPI types.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import qaStreamV2Frames from '../../../docs/api/fixtures/qa-stream-v2-frames.json'
import { parseQaStreamEvent } from '@/api/qaStream'
import type { components } from '@/api/generated/schema'
import type { QaStreamCitationData } from '@/api/types'
import { appendUniqueCitation, citationDisplayId, citationKey, citationNodeId } from '@/utils/qaCitations'

type Schema = components['schemas']

const repoRoot = resolve(__dirname, '../../..')
const openapiYaml = readFileSync(resolve(repoRoot, 'docs/api/openapi.yaml'), 'utf-8')

describe('QA SSE V2 cross-layer integration', () => {
  it('OpenAPI documents QaStreamCitation discriminator variants', () => {
    expect(openapiYaml).toContain('QaStreamCitationNode')
    expect(openapiYaml).toContain('QaStreamCitationEdge')
    expect(openapiYaml).toContain('QaStreamCitationChunk')
    expect(openapiYaml).toContain('QaStreamCitationPage')
    expect(openapiYaml).toContain('propertyName: type')
  })

  it('parses fixture frames into typed server events', () => {
    const parsed = qaStreamV2Frames.map((frame) => parseQaStreamEvent(frame.event, JSON.stringify(frame.data)))
    expect(parsed.every((item) => item !== null)).toBe(true)

    const citations = parsed.filter((item) => item?.type === 'citation')
    expect(citations).toHaveLength(4)
    const types = citations.map((item) => (item?.type === 'citation' ? item.data.type : null))
    expect(types).toEqual(['node', 'edge', 'chunk', 'page'])
  })

  it('assigns stable keys and display ids for all citation types', () => {
    const citations: QaStreamCitationData[] = []
    for (const frame of qaStreamV2Frames) {
      if (frame.event !== 'citation') continue
      const parsed = parseQaStreamEvent(frame.event, JSON.stringify(frame.data))
      if (parsed?.type !== 'citation') continue
      const next = appendUniqueCitation(citations, parsed.data)
      expect(next.length).toBe(citations.length + 1)
      citations.splice(0, citations.length, ...next)
    }

    expect(citations).toHaveLength(4)
    const keys = new Set(citations.map((item) => citationKey(item)))
    expect(keys.size).toBe(4)

    for (const citation of citations) {
      expect(citationDisplayId(citation)).toBeTruthy()
      if (citation.type === 'node') {
        expect(citationNodeId(citation)).toBe(citation.node_id)
      } else {
        expect(citationNodeId(citation)).toBeNull()
      }
    }
  })

  it('fixture node citation satisfies generated OpenAPI schema alias', () => {
    const nodeFrame = qaStreamV2Frames.find((frame) => frame.event === 'citation' && frame.data.type === 'node')
    expect(nodeFrame).toBeDefined()
    const parsed = parseQaStreamEvent('citation', JSON.stringify(nodeFrame!.data))
    expect(parsed?.type).toBe('citation')
    if (parsed?.type !== 'citation') return

    const _schemaCheck: Schema['QaStreamCitationNode'] = parsed.data as Schema['QaStreamCitationNode']
    expect(_schemaCheck.type).toBe('node')
    expect(_schemaCheck.node_id).toBe('n1')
  })
})
