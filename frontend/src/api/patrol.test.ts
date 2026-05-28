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

  it('runPatrol returns DataResponse<PatrolReport> from postData', async () => {
    const envelope: DataResponse<PatrolReport> = {
      data: {
        mode: 'lens_clash',
        paper_ids: ['hss-001', 'stem-001'],
        insights: [],
        generated_at: '2026-05-19T11:00:00Z',
      },
      meta: { request_id: 'req-patrol' },
    }
    mockPostData.mockResolvedValue(envelope)

    const result = await runPatrol(['hss-001', 'stem-001'])

    expect(mockPostData).toHaveBeenCalledWith('/patrol', { paper_ids: ['hss-001', 'stem-001'] })
    expect(result).toEqual(envelope)
    expect(result.data.mode).toBe('lens_clash')
  })
})
