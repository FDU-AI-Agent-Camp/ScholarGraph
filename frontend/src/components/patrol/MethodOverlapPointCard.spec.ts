/**
 * Unit / boundary / 越权 — Part F / F9: point-level node_refs on MethodOverlapPointCard.
 * RED until the card embeds graph deep links for structured_points[].node_refs.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { components } from '@/api/types'
import MethodOverlapPointCard from '@/components/patrol/MethodOverlapPointCard.vue'
import { RouteName } from '@/router/meta'

type MethodOverlapPoint = components['schemas']['MethodOverlapPoint']

const RouterLinkStub = {
  props: ['to'],
  template: '<a class="router-link-stub" :data-to="JSON.stringify(to)"><slot /></a>',
}

function basePoint(overrides: Partial<MethodOverlapPoint> = {}): MethodOverlapPoint {
  return {
    mode: 'method_overlap',
    overlap_type: 'method',
    overlap_label: 'PCA',
    paper_a_usage: 'usage-a',
    paper_b_usage: 'usage-b',
    overlap_score: 0.99,
    match_type: 'semantic',
    node_refs: [
      { paper_id: 'stem-001', node_id: 'n_method_pca', label: 'PCA' },
      { paper_id: 'stem-002', node_id: 'n_method_pca_full', label: 'Principal Component Analysis' },
    ],
    ...overrides,
  }
}

describe('MethodOverlapPointCard point node_refs (F9 unit)', () => {
  it('renders point-level node_refs as PaperGraph deep links', () => {
    const wrapper = mount(MethodOverlapPointCard, {
      props: { point: basePoint() },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    const links = wrapper.findAll('[data-testid="patrol-point-node-ref"]')
    expect(links).toHaveLength(2)
    expect(wrapper.text()).toContain('PCA')
    expect(wrapper.text()).toContain('Principal Component Analysis')
    expect(wrapper.text()).toContain('n_method_pca')

    const firstTo = JSON.parse(links[0]!.attributes('data-to')!) as {
      name: string
      params: { paperId: string }
      query: { node: string }
    }
    expect(firstTo.name).toBe(RouteName.PaperGraph)
    expect(firstTo.params.paperId).toBe('stem-001')
    expect(firstTo.query.node).toBe('n_method_pca')
  })

  it('skips malformed refs missing paper_id or node_id (越权/脏数据边界)', () => {
    const wrapper = mount(MethodOverlapPointCard, {
      props: {
        point: basePoint({
          node_refs: [
            { paper_id: '', node_id: 'n_bad', label: 'bad-empty-paper' },
            { paper_id: 'stem-001', node_id: '', label: 'bad-empty-node' },
            { paper_id: 'stem-001', node_id: 'n_ok', label: 'ok-ref' },
          ] as MethodOverlapPoint['node_refs'],
        }),
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    const links = wrapper.findAll('[data-testid="patrol-point-node-ref"]')
    expect(links).toHaveLength(1)
    expect(wrapper.text()).toContain('ok-ref')
    expect(wrapper.text()).not.toContain('bad-empty-paper')
    expect(wrapper.text()).not.toContain('bad-empty-node')
  })

  it('renders structured fields without point-ref links when node_refs is empty (boundary)', () => {
    const wrapper = mount(MethodOverlapPointCard, {
      props: { point: basePoint({ node_refs: [] }) },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.text()).toContain('usage-a')
    expect(wrapper.text()).toContain('usage-b')
    expect(wrapper.findAll('[data-testid="patrol-point-node-ref"]')).toHaveLength(0)
    expect(wrapper.findAll('.router-link-stub')).toHaveLength(0)
  })
})
