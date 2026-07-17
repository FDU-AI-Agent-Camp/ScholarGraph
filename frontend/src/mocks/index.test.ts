/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import * as mocks from '@/mocks'
import papersListFixture from '../../../docs/api/fixtures/papers-list.json'

describe('src/mocks re-exports', () => {
  it('papersList matches canonical docs/api fixture', () => {
    expect(mocks.papersList).toEqual(papersListFixture)
  })

  it('exports failed status fixture with error_code', () => {
    expect(mocks.paperStatusFailed.data.error_code).toBe('LLM_JSON_INVALID')
  })

  it('exports V2 QA SSE frame fixture', () => {
    expect(mocks.qaStreamV2Frames).toHaveLength(6)
    expect(mocks.qaStreamV2Frames[1]?.event).toBe('citation')
    expect(mocks.qaStreamV2Frames[1]?.data.type).toBe('node')
  })

  it('exports V2 Patrol fixtures with structured_points (F11)', () => {
    expect(mocks.patrolMethodOverlap.data.mode).toBe('method_overlap')
    expect(mocks.patrolClaimEvolution.data.mode).toBe('claim_evolution')
    expect(mocks.patrolLensClash.data.mode).toBe('lens_clash')
    expect(mocks.patrolMethodOverlap.data.insights[0]?.structured_points?.[0]?.mode).toBe('method_overlap')
    expect(mocks.patrolClaimEvolution.data.insights[0]?.structured_points?.[0]?.mode).toBe('claim_evolution')
  })
})
