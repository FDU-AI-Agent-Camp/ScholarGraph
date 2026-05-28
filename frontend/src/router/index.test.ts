import { describe, expect, it } from 'vitest'

import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import router from '@/router/index'

describe('router', () => {
  it('registers routes with typed meta titles', () => {
    const papers = router.getRoutes().find((r) => r.name === RouteName.Papers)
    expect(papers?.meta.title).toBe('文献库')
    expect(papers?.meta.nav).toBe(true)

    const detail = router.getRoutes().find((r) => r.name === RouteName.PaperDetail)
    expect(detail?.meta.title).toBe('论文详情')
  })

  it('defines paper detail props mapper on route record', () => {
    const detail = routes.find((r) => r.name === RouteName.PaperDetail)
    expect(typeof detail?.props).toBe('function')
    if (typeof detail?.props === 'function') {
      const result = detail.props({
        params: { paperId: 'hss-001' },
      } as never)
      expect(result).toEqual({ paperId: 'hss-001' })
    }
  })

  it('maps graph route props and marks nav entries', () => {
    const graph = routes.find((r) => r.name === RouteName.PaperGraph)
    expect(graph?.meta?.title).toBe('知识图谱')
    if (typeof graph?.props === 'function') {
      expect(graph.props({ params: { paperId: 'stem-001' } } as never)).toEqual({
        paperId: 'stem-001',
      })
    }

    const navNames = routes.filter((r) => r.meta?.nav).map((r) => r.name)
    expect(navNames).toEqual([RouteName.Home, RouteName.Papers, RouteName.Patrol])
  })
})
