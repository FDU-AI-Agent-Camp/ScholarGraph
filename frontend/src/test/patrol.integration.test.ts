/**
 * Patrol integration: fixture envelope ↔ API client ↔ form helpers ↔ demo path.
 */
import { describe, expect, it, vi } from 'vitest'

import * as client from '@/api/client'
import { runPatrol } from '@/api/patrol'
import type { DataResponse, PatrolReport } from '@/api/types'
import { formatPatrolError, parsePatrolPaperIds, validatePatrolPaperIds } from '@/utils/patrolForm'
import patrolFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'
import packageJson from '../../package.json'

describe('patrol integration (fixtures + API + form)', () => {
  it('chains patrol-lens-clash fixture through runPatrol with default mode', async () => {
    const postSpy = vi.spyOn(client, 'postData').mockResolvedValue(patrolFixture as DataResponse<PatrolReport>)

    const paperIds = parsePatrolPaperIds('hss-001, hss-002')
    expect(validatePatrolPaperIds(paperIds)).toBeNull()

    const result = await runPatrol(paperIds)

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['hss-001', 'hss-002'],
      mode: 'lens_clash',
    })
    expect(result.data.generated_at).toBe('2026-05-19T11:00:00Z')
    expect(result.data.insights[0]?.node_refs).toEqual([
      { paper_id: 'hss-001', node_id: 'n_lens_a', label: '消费社会' },
      { paper_id: 'hss-002', node_id: 'n_lens_b', label: '公共领域' },
    ])
    postSpy.mockRestore()
  })

  it('forwards contradiction mode to POST /patrol', async () => {
    const postSpy = vi.spyOn(client, 'postData').mockResolvedValue({
      data: {
        mode: 'contradiction',
        paper_ids: ['hss-001', 'hss-002'],
        insights: [],
        generated_at: '2026-05-19T12:00:00Z',
      },
      meta: { request_id: 'req-contradiction' },
    })

    const result = await runPatrol(['hss-001', 'hss-002'], { mode: 'contradiction' })

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['hss-001', 'hss-002'],
      mode: 'contradiction',
    })
    expect(result.data.mode).toBe('contradiction')
    postSpy.mockRestore()
  })

  it('maps patrol error codes to operator hints for PatrolView', () => {
    expect(formatPatrolError('GRAPH_NOT_READY', '图谱未就绪')).toContain('seed-demo-graphs')
    expect(formatPatrolError('PATROL_INSUFFICIENT_DATA', '数据不足')).toContain('切换巡检模式')
    expect(formatPatrolError(null, '未知错误')).toBe('未知错误')
  })

  it('documents demo:setup script for browser full-path rehearsal', () => {
    expect(packageJson.scripts['demo:setup']).toContain('run_frontend_demo.py')
  })
})
