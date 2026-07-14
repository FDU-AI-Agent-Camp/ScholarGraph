/**
 * Patrol integration: fixture envelope ↔ API client ↔ form helpers ↔ demo path.
 */
import { describe, expect, it, vi } from 'vitest'

import * as client from '@/api/client'
import { runPatrol } from '@/api/patrol'
import type { DataResponse, PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import {
  formatPatrolError,
  parsePatrolPaperIds,
  resolvePatrolApiError,
  validatePatrolPaperIds,
  validatePatrolSelection,
} from '@/utils/patrolForm'
import patrolFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'
import patrolMethodOverlapFixture from '../../../docs/api/fixtures/patrol-method-overlap.json'
import patrolClaimEvolutionFixture from '../../../docs/api/fixtures/patrol-claim-evolution.json'
import packageJson from '../../package.json'

describe('patrol integration (fixtures + API + form)', () => {
  it('chains patrol-lens-clash fixture through runPatrol with default mode', async () => {
    const postSpy = vi.spyOn(client, 'postData').mockResolvedValue(patrolFixture as DataResponse<PatrolReport>)

    const paperIds = parsePatrolPaperIds('hss-001, hss-002')
    expect(validatePatrolPaperIds(paperIds)).toBeNull()
    expect(validatePatrolSelection('hss-001', 'hss-002')).toBeNull()

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

  it('forwards method_overlap mode with V2 fixture structured_points', async () => {
    const postSpy = vi
      .spyOn(client, 'postData')
      .mockResolvedValue(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const result = await runPatrol(['stem-001', 'stem-002'], { mode: 'method_overlap' })

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['stem-001', 'stem-002'],
      mode: 'method_overlap',
    })
    const point = result.data.insights[0]?.structured_points?.[0]
    expect(point?.mode).toBe('method_overlap')
    postSpy.mockRestore()
  })

  it('forwards claim_evolution mode with V2 fixture structured_points', async () => {
    const postSpy = vi
      .spyOn(client, 'postData')
      .mockResolvedValue(patrolClaimEvolutionFixture as DataResponse<PatrolReport>)

    const result = await runPatrol(['stem-001', 'stem-002'], { mode: 'claim_evolution' })

    expect(postSpy).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['stem-001', 'stem-002'],
      mode: 'claim_evolution',
    })
    const point = result.data.insights[0]?.structured_points?.[0]
    expect(point?.mode).toBe('claim_evolution')
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

  it('maps patrol error codes to baseline presentation for PatrolView', () => {
    const graphNotReady = resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪')
    expect(graphNotReady.ctaKind).toBe('papers')
    expect(graphNotReady.title).toBe(PATROL_BASELINE_COPY.graphNotReadyTitle)
    expect(graphNotReady.ctaLabel).toBe(PATROL_BASELINE_COPY.graphNotReadyCta)

    const insufficientData = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
    expect(insufficientData.title).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(insufficientData.description).toBe(PATROL_BASELINE_COPY.insufficientDataDescription)
    expect(insufficientData.ctaLabel).toBe(PATROL_BASELINE_COPY.insufficientDataCta)
    expect(insufficientData.ctaKind).toBe('reset-selection')

    expect(formatPatrolError('GRAPH_NOT_READY', '图谱未就绪')).toContain(PATROL_BASELINE_COPY.graphNotReadyTitle)
  })

  it('§1.4.4 baseline copy table matches patrolCopy constants', () => {
    expect(PATROL_BASELINE_COPY.subtitle).toBe('跨论文探测理论视角冲突与论点矛盾 · 需 2 篇 ready 论文')
    expect(PATROL_BASELINE_COPY.runButton).toBe('运行巡检')
    expect(PATROL_BASELINE_COPY.runButtonLoading).toBe('分析中…')
    expect(PATROL_BASELINE_COPY.insufficientDataTitle).toBe('数据不足')
    expect(PATROL_BASELINE_COPY.insufficientDataDescription).toBe('换用 ready 状态的论文再试')
    expect(PATROL_BASELINE_COPY.validationExactTwo).toBe('请输入恰好 2 个 paper_id')
  })

  it('blocks duplicate paper ids in validatePatrolSelection before POST /patrol', () => {
    expect(validatePatrolSelection('hss-001', 'hss-001')).toBe(PATROL_BASELINE_COPY.validationDuplicate('hss-001'))
    expect(validatePatrolPaperIds(['hss-001', 'hss-001'])).toBe(PATROL_BASELINE_COPY.validationDuplicate('hss-001'))
  })

  it('documents demo:setup script for browser full-path rehearsal', () => {
    expect(packageJson.scripts['demo:setup']).toContain('run_frontend_demo.py')
  })
})
