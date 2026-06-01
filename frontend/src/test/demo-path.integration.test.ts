/**
 * design-spec §16 / ui-design-progress §6 — 答辩路径路由链集成冒烟。
 */
import { describe, expect, it } from 'vitest'

import { routes } from '@/router/index'
import { readFrontendSource } from '@/test/helpers/designTokens'

const homeViewSrc = readFrontendSource('views/HomeView.vue')
const detailViewSrc = readFrontendSource('views/PaperDetailView.vue')
const graphViewSrc = readFrontendSource('views/PaperGraphView.vue')
const patrolViewSrc = readFrontendSource('views/PatrolView.vue')

describe('§6 demo defense path integration', () => {
  it('registers ordered routes for the defense walkthrough', () => {
    const paths = routes.map((route) => route.path)
    expect(paths).toContain('/')
    expect(paths).toContain('/papers')
    expect(paths).toContain('/papers/:paperId')
    expect(paths).toContain('/papers/:paperId/graph')
    expect(paths).toContain('/patrol')
  })

  it('Home CTAs enter Papers list and Lens Clash patrol demo', () => {
    expect(homeViewSrc).toMatch(/to="\/papers"/)
    expect(homeViewSrc).toMatch(/to="\/patrol"/)
    expect(homeViewSrc).toContain('Lens Clash')
  })

  it('Detail exposes full-graph navigation into Graph deep-link route', () => {
    expect(detailViewSrc).toContain('RouteName.PaperGraph')
    expect(detailViewSrc).toContain('node: highlightNodeId.value')
    expect(graphViewSrc).toContain('route.query.node')
  })

  it('Patrol node_refs link back to Graph with node query for deep-link handoff', () => {
    expect(patrolViewSrc).toContain('graphLinkForNodeRef')
    expect(patrolViewSrc).toContain('query: { node: ref.node_id }')
    expect(patrolViewSrc).toContain('RouteName.PaperGraph')
  })

  it('Graph not-ready and Patrol errors keep actionable return paths', () => {
    expect(graphViewSrc).toContain('graph-view__error-cta')
    expect(patrolViewSrc).toContain('patrol-view__error-cta')
    expect(patrolViewSrc).toContain('onErrorCta')
  })
})
