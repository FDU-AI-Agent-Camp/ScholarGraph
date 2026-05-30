import { describe, expect, it } from 'vitest'

import { parsePatrolPaperIds, validatePatrolPaperIds, formatPatrolError } from './patrolForm'

describe('parsePatrolPaperIds', () => {
  it('splits comma-separated ids and trims whitespace', () => {
    expect(parsePatrolPaperIds(' hss-001 , hss-002 ')).toEqual(['hss-001', 'hss-002'])
  })

  it('returns empty array for blank input', () => {
    expect(parsePatrolPaperIds('  ,  ')).toEqual([])
  })
})

describe('validatePatrolPaperIds', () => {
  it('requires exactly two paper ids', () => {
    expect(validatePatrolPaperIds(['hss-001'])).toMatch(/恰好 2/)
    expect(validatePatrolPaperIds(['hss-001', 'hss-002', 'hss-003'])).toMatch(/恰好 2/)
    expect(validatePatrolPaperIds(['hss-001', 'hss-002'])).toBeNull()
  })
})

describe('formatPatrolError', () => {
  it('adds seed hint for GRAPH_NOT_READY', () => {
    expect(formatPatrolError('GRAPH_NOT_READY', '图谱未就绪')).toContain('--seed-demo-graphs')
  })

  it('adds mode hint for PATROL_INSUFFICIENT_DATA', () => {
    expect(formatPatrolError('PATROL_INSUFFICIENT_DATA', '数据不足')).toContain('切换巡检模式')
  })

  it('returns message unchanged for unknown codes', () => {
    expect(formatPatrolError('PATROL_FAILED', '巡检失败')).toBe('巡检失败')
  })
})
