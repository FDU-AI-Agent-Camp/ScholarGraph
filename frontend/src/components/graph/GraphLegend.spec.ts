import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { UnifiedPaperGraph } from '@/api/types'
import GraphLegend from '@/components/graph/GraphLegend.vue'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'

const sampleGraph: UnifiedPaperGraph = {
  paper_id: 'hss-001',
  paradigm: 'HSS',
  nodes: [
    { id: 'n1', label: '核心论点', type: 'Thesis', data: {} },
    { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
  ],
  edges: [],
}

describe('GraphLegend', () => {
  it('renders baseline caption and unique node type swatches', () => {
    const wrapper = mount(GraphLegend, { props: { graph: sampleGraph } })

    expect(wrapper.find('.graph-legend__title').text()).toBe(GRAPH_BASELINE_COPY.legendTitle)
    expect(wrapper.findAll('.graph-legend__item')).toHaveLength(2)
    expect(wrapper.find('.graph-legend').attributes('aria-label')).toBe('图谱节点类型图例')
  })
})
