/**
 * G.6 OpenAPI / fixtures 前端专项：classify_warnings 字段与 generated schema。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import type { PaperDetail, PaperStatusData } from '@/api/types'
import { CLASSIFIER_HEURISTIC_FALLBACK_CODE } from '@/utils/classifyWarnings'

import classifyFallbackDetailFixture from '../../../docs/api/fixtures/paper-detail-classify-fallback.json'
import classifyFallbackStatusFixture from '../../../docs/api/fixtures/paper-status-classify-fallback.json'

const repoRoot = resolve(import.meta.dirname, '../../..')
const openapiYaml = readFileSync(resolve(repoRoot, 'docs/api/openapi.yaml'), 'utf-8')
const generatedSchema = readFileSync(
  resolve(repoRoot, 'frontend/src/api/generated/schema.d.ts'),
  'utf-8',
)

describe('Phase G G.6 OpenAPI / fixtures (frontend)', () => {
  it('OpenAPI documents classify_warnings on PaperStatusData and PaperDetail', () => {
    expect(openapiYaml).toContain('classify_warnings:')
    expect(openapiYaml).toContain('classifier_heuristic_fallback')
    expect(openapiYaml).toContain('PaperStatusData:')
    expect(openapiYaml).toContain('PaperDetail:')
  })

  it('generated schema.d.ts includes classify_warnings', () => {
    expect(generatedSchema).toContain('classify_warnings')
  })

  it('status classify-fallback fixture validates expected shape', () => {
    const data = classifyFallbackStatusFixture.data as PaperStatusData
    expect(Array.isArray(data.classify_warnings)).toBe(true)
    expect(data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
  })

  it('detail classify-fallback fixture validates expected shape', () => {
    const data = classifyFallbackDetailFixture.data as PaperDetail
    expect(data.classify_warnings).toEqual([CLASSIFIER_HEURISTIC_FALLBACK_CODE])
    expect(data.classification?.paradigm).toBeTruthy()
  })

  it('ParadigmClassification in OpenAPI has no classify_warnings property block', () => {
    const paradigmBlock = openapiYaml.split('ParadigmClassification:')[1]?.split('\n    PaperDetail:')[0] ?? ''
    expect(paradigmBlock).toContain('paradigm:')
    expect(paradigmBlock).toContain('confidence:')
    expect(paradigmBlock).toContain('reason:')
    expect(paradigmBlock).not.toContain('classify_warnings')
  })
})
