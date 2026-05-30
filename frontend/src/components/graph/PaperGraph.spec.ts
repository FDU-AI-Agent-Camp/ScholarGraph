import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UnifiedPaperGraph } from '@/api/types'

const graphMocks = vi.hoisted(() => ({
  render: vi.fn().mockResolvedValue(undefined),
  destroy: vi.fn(),
  setElementState: vi.fn().mockResolvedValue(undefined),
  focusElement: vi.fn().mockResolvedValue(undefined),
  on: vi.fn(),
  setSize: vi.fn(),
}))

vi.mock('@antv/g6', () => ({
  Graph: vi.fn(function GraphMock() {
    return graphMocks
  }),
  NodeEvent: { CLICK: 'node:click' },
}))

import PaperGraph from '@/components/graph/PaperGraph.vue'

const sampleGraph: UnifiedPaperGraph = {
  paper_id: 'hss-001',
  paradigm: 'HSS',
  nodes: [
    { id: 'n1', label: '核心论点', type: 'Thesis', data: {} },
    { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
  ],
  edges: [],
}

describe('PaperGraph', () => {
  beforeEach(() => {
    graphMocks.render.mockClear()
    graphMocks.destroy.mockClear()
    graphMocks.setElementState.mockClear()
    graphMocks.focusElement.mockClear()
    graphMocks.on.mockClear()
    graphMocks.setSize.mockClear()

    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe(): void {}
        disconnect(): void {}
      },
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders G6 graph from API graph payload', async () => {
    mount(PaperGraph, {
      props: { graph: sampleGraph },
      attachTo: document.body,
    })

    await flushPromises()

    expect(graphMocks.render).toHaveBeenCalled()
    expect(graphMocks.on).toHaveBeenCalled()
  })

  it('applies active highlight when highlightNodeId changes', async () => {
    const wrapper = mount(PaperGraph, {
      props: { graph: sampleGraph, highlightNodeId: null },
      attachTo: document.body,
    })

    await flushPromises()
    graphMocks.setElementState.mockClear()

    await wrapper.setProps({ highlightNodeId: 'n2' })
    await flushPromises()

    expect(graphMocks.setElementState).toHaveBeenCalledWith({
      n1: [],
      n2: 'active',
    })
    expect(graphMocks.focusElement).toHaveBeenCalledWith('n2')
  })
})
