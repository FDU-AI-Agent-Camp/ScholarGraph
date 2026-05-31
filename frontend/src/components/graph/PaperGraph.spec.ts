import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UnifiedPaperGraph } from '@/api/types'
import {
  GRAPH_ACTIVE_LINE_WIDTH,
  GRAPH_HOVER_LINE_WIDTH,
  GRAPH_NODE_RADIUS,
  GRAPH_STATE_ANIMATION_MS,
  buildG6Behaviors,
  buildG6NodeStyleOptions,
  resolvePaperGraphThemeTokens,
  GRAPH_EDGE_STROKE,
} from '@/utils/paperGraph'

const { graphMocks, graphConstructorOptions } = vi.hoisted(() => {
  const options = { value: null as Record<string, unknown> | null }
  const mocks = {
    render: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
    setElementState: vi.fn().mockResolvedValue(undefined),
    focusElement: vi.fn().mockResolvedValue(undefined),
    on: vi.fn(),
    setSize: vi.fn(),
    zoomBy: vi.fn().mockResolvedValue(undefined),
    fitView: vi.fn().mockResolvedValue(undefined),
    layout: vi.fn().mockResolvedValue(undefined),
  }
  return { graphMocks: mocks, graphConstructorOptions: options }
})

vi.mock('@antv/g6', () => ({
  Graph: vi.fn(function GraphMock(graphOptions: Record<string, unknown>) {
    graphConstructorOptions.value = graphOptions
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
    graphConstructorOptions.value = null

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

  it('configures rect nodes with type colors, hover/active states, and 120ms stroke animation', async () => {
    mount(PaperGraph, {
      props: { graph: sampleGraph },
      attachTo: document.body,
    })

    await flushPromises()

    const options = graphConstructorOptions.value
    const nodeOptions = options?.node as {
      type?: string
      style?: { radius?: number }
      state?: { hover?: { lineWidth?: number }; active?: { lineWidth?: number; stroke?: string } }
      animation?: { update?: Array<{ duration?: number; fields?: string[] }> }
    }

    expect(nodeOptions?.type).toBe('rect')
    expect(nodeOptions?.style?.radius).toBe(GRAPH_NODE_RADIUS)
    expect(nodeOptions?.state?.hover?.lineWidth).toBe(GRAPH_HOVER_LINE_WIDTH)
    expect(nodeOptions?.state?.active?.lineWidth).toBe(GRAPH_ACTIVE_LINE_WIDTH)
    expect(nodeOptions?.state?.active?.stroke).toBe('#e11d48')
    expect(nodeOptions?.animation?.update?.[0]?.duration).toBe(GRAPH_STATE_ANIMATION_MS)
    expect(nodeOptions?.animation?.update?.[0]?.fields).toContain('stroke')

    const behaviors = options?.behaviors as Array<string | { type?: string; state?: string }>
    expect(
      behaviors.some((item) => typeof item === 'object' && item.type === 'hover-activate' && item.state === 'hover'),
    ).toBe(true)

    const edgeOptions = options?.edge as { style?: { stroke?: string; lineWidth?: number } }
    expect(edgeOptions?.style?.stroke).toBe(GRAPH_EDGE_STROKE)
    expect(edgeOptions?.style?.lineWidth).toBe(1)
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

  it('renders legend overlay and canvas background in compact mode', async () => {
    const wrapper = mount(PaperGraph, {
      props: { graph: sampleGraph, compact: true },
      attachTo: document.body,
    })

    await flushPromises()

    expect(wrapper.find('.paper-graph.compact').exists()).toBe(true)
    expect(wrapper.find('.graph-host.compact').exists()).toBe(true)
    expect(wrapper.find('.graph-legend').exists()).toBe(true)
    expect(wrapper.find('.paper-graph__legend').exists()).toBe(true)
  })

  it('uses full-bleed canvas host without dashed border', async () => {
    const wrapper = mount(PaperGraph, {
      props: { graph: sampleGraph, fullBleed: true },
      attachTo: document.body,
    })

    await flushPromises()

    expect(wrapper.find('.paper-graph--full-bleed').exists()).toBe(true)
    expect(wrapper.find('.graph-host--full-bleed').exists()).toBe(true)
  })

  it('exposes toolbar viewport helpers', async () => {
    const wrapper = mount(PaperGraph, {
      props: { graph: sampleGraph },
      attachTo: document.body,
    })

    await flushPromises()

    const exposed = wrapper.vm as unknown as {
      zoomIn: () => Promise<void>
      zoomOut: () => Promise<void>
      fitView: () => Promise<void>
      resetLayout: () => Promise<void>
    }

    await exposed.zoomIn()
    await exposed.zoomOut()
    await exposed.fitView()
    await exposed.resetLayout()

    expect(graphMocks.zoomBy).toHaveBeenCalled()
    expect(graphMocks.fitView).toHaveBeenCalled()
    expect(graphMocks.layout).toHaveBeenCalled()
  })
})

describe('paperGraph G6 style helpers', () => {
  it('buildG6NodeStyleOptions maps theme tokens to hover/active stroke widths', () => {
    const theme = resolvePaperGraphThemeTokens((_name, fallback) => fallback)
    const options = buildG6NodeStyleOptions(theme, () => 'label')

    expect(options.type).toBe('rect')
    expect(options.state.hover.lineWidth).toBe(GRAPH_HOVER_LINE_WIDTH)
    expect(options.state.active.lineWidth).toBe(GRAPH_ACTIVE_LINE_WIDTH)
    expect(options.state.active.stroke).toBe(theme.activeStroke)
  })

  it('buildG6Behaviors keeps hover on separate state from citation active', () => {
    const behaviors = buildG6Behaviors()
    const hoverBehavior = behaviors.find((item) => typeof item === 'object' && item.type === 'hover-activate')

    expect(hoverBehavior).toMatchObject({ type: 'hover-activate', state: 'hover' })
  })
})
