import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DataResponse, PatrolReport } from '@/api/types'

const mockPostData = vi.fn()

vi.mock('./client', () => ({
  postData: (...args: unknown[]) => mockPostData(...args),
}))

import { runPatrol } from '@/api/patrol'

describe('patrol API module', () => {
  beforeEach(() => {
    mockPostData.mockReset()
  })

  it('runPatrol sends paper_ids and default mode lens_clash', async () => {
    const envelope: DataResponse<PatrolReport> = {
      data: {
        mode: 'lens_clash',
        paper_ids: ['hss-001', 'hss-002'],
        insights: [],
        generated_at: '2026-05-19T11:00:00Z',
      },
      meta: { request_id: 'req-patrol' },
    }
    mockPostData.mockResolvedValue(envelope)

    const result = await runPatrol(['hss-001', 'hss-002'])

    expect(mockPostData).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['hss-001', 'hss-002'],
      mode: 'lens_clash',
    })
    expect(result).toEqual(envelope)
  })

  it('runPatrol forwards explicit mode', async () => {
    mockPostData.mockResolvedValue({
      data: {
        mode: 'contradiction',
        paper_ids: ['hss-001', 'hss-002'],
        insights: [],
        generated_at: '2026-05-19T11:00:00Z',
      },
      meta: { request_id: 'req-patrol' },
    })

    await runPatrol(['hss-001', 'hss-002'], { mode: 'contradiction' })

    expect(mockPostData).toHaveBeenCalledWith('/patrol', {
      paper_ids: ['hss-001', 'hss-002'],
      mode: 'contradiction',
    })
  })

  it.each([
    ['method_overlap', ['stem-001', 'stem-002']] as const,
    ['claim_evolution', ['stem-001', 'stem-002']] as const,
  ])('runPatrol forwards V2 mode %s (接口)', async (mode, paperIds) => {
    mockPostData.mockResolvedValue({
      data: {
        mode,
        paper_ids: paperIds,
        insights: [],
        generated_at: '2026-07-14T00:00:00Z',
      },
      meta: { request_id: `req-patrol-${mode}` },
    })

    await runPatrol([...paperIds], { mode })

    expect(mockPostData).toHaveBeenCalledWith('/patrol', {
      paper_ids: [...paperIds],
      mode,
    })
  })
})
