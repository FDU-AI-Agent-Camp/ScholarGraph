/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Unit / interface — Part F residual F-R3: production PATROL_BASELINE_COPY point-field keys.
 * Exercises the real constants module (not test helpers).
 */
import { describe, expect, it } from 'vitest'

import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

const POINT_FIELD_KEYS = [
  'pointFieldPaperA',
  'pointFieldPaperB',
  'pointFieldDataset',
  'pointFieldScore',
  'pointFieldMatch',
  'pointFieldEvidence',
  'pointFieldFit',
  'pointFieldLensA',
  'pointFieldLensB',
  'pointFieldAspect',
  'pointFieldPointA',
  'pointFieldPointB',
  'pointFieldConflict',
] as const

function pointField(key: (typeof POINT_FIELD_KEYS)[number]): unknown {
  return (PATROL_BASELINE_COPY as Record<string, unknown>)[key]
}

describe('PATROL_BASELINE_COPY point field labels (F-R3 unit)', () => {
  it('defines Chinese labels for method_overlap / claim_evolution fields (接口)', () => {
    for (const key of [
      'pointFieldPaperA',
      'pointFieldPaperB',
      'pointFieldDataset',
      'pointFieldScore',
      'pointFieldMatch',
      'pointFieldEvidence',
      'pointFieldFit',
    ] as const) {
      expect(key in PATROL_BASELINE_COPY, `missing ${key}`).toBe(true)
    }
    expect(pointField('pointFieldPaperA')).toBe('论文 A')
    expect(pointField('pointFieldPaperB')).toBe('论文 B')
    expect(pointField('pointFieldDataset')).toBe('数据集')
    expect(pointField('pointFieldScore')).toBe('重叠分')
    expect(pointField('pointFieldMatch')).toBe('匹配')
    expect(pointField('pointFieldEvidence')).toBe('证据')
    expect(pointField('pointFieldFit')).toBe('问题契合')
  })

  it('defines Chinese labels for lens_clash / contradiction fields (接口)', () => {
    expect(pointField('pointFieldLensA')).toBe('视角 A')
    expect(pointField('pointFieldLensB')).toBe('视角 B')
    expect(pointField('pointFieldAspect')).toBe('冲突面')
    expect(pointField('pointFieldPointA')).toBe('论点 A')
    expect(pointField('pointFieldPointB')).toBe('论点 B')
    expect(pointField('pointFieldConflict')).toBe('冲突类型')
  })

  it('labels are non-empty product Chinese and not English leftovers (越权/边界)', () => {
    for (const key of POINT_FIELD_KEYS) {
      const label = pointField(key)
      expect(label, key).toEqual(expect.any(String))
      expect((label as string).trim().length).toBeGreaterThan(0)
      expect(label as string).not.toMatch(/^(Paper|Score|Evidence|Lens|Fit|Match|Dataset|Aspect|Point)\b/)
    }
  })
})
