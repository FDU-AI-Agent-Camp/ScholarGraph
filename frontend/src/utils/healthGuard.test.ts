/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import type { PatrolServiceHealth } from '@/api/types'
import { isPatrolDemoPath, isRerankerReady, shouldWarnRerankerOnPatrolDemo } from '@/utils/healthGuard'

function patrol(overrides: Partial<PatrolServiceHealth> = {}): PatrolServiceHealth {
  return {
    status: 'fully_functional',
    claim_rq_funnel_enabled: true,
    reranker_status: 'READY',
    active_profile: 'demo',
    ...overrides,
  }
}

describe('healthGuard', () => {
  it('detects patrol demo paths', () => {
    expect(isPatrolDemoPath('/patrol')).toBe(true)
    expect(isPatrolDemoPath('/papers')).toBe(false)
  })

  it('warns on patrol demo when reranker is not READY', () => {
    const service = patrol({ reranker_status: 'DISABLED_FALLBACK_ACTIVE', status: 'degraded' })
    expect(shouldWarnRerankerOnPatrolDemo(service, '/patrol')).toBe(true)
  })

  it('does not warn outside patrol demo path', () => {
    const service = patrol({ reranker_status: 'DISABLED_FALLBACK_ACTIVE' })
    expect(shouldWarnRerankerOnPatrolDemo(service, '/papers')).toBe(false)
  })

  it('does not warn when reranker is READY', () => {
    expect(isRerankerReady('READY')).toBe(true)
    expect(shouldWarnRerankerOnPatrolDemo(patrol(), '/patrol')).toBe(false)
  })

  it('does not warn in mock local reranker mode on patrol path', () => {
    const service = patrol({ reranker_status: 'MOCK_LOCAL' })
    expect(shouldWarnRerankerOnPatrolDemo(service, '/patrol')).toBe(false)
  })
})
