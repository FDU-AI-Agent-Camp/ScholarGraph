import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UnifiedPaperGraph } from '@/api/types'
import {
  GRAPH_ACTIVE_LINE_WIDTH,
  GRAPH_COMPACT_HEIGHT,
  GRAPH_DEFAULT_HEIGHT,
  GRAPH_FIT_VIEW_DEBOUNCE_MS,
  GRAPH_FIT_VIEW_PADDING_COMPACT,
  GRAPH_FIT_VIEW_PADDING_DEFAULT,
  GRAPH_FULL_MIN_HEIGHT,
  GRAPH_HOVER_LINE_WIDTH,
  GRAPH_NODE_RADIUS,
  GRAPH_STATE_ANIMATION_MS,
  buildG6Behaviors,
  buildG6LayoutOptions,
  buildG6NodeStyleOptions,
  resolvePaperGraphThemeTokens,
  GRAPH_EDGE_STROKE,
} from '@/utils/paperGraph'

const { graphMocks, graphConstructorOptions, resizeObserverCallbackRef } = vi.hoisted(() => {
  const options = { value: null as Record<string, unknown> | null }
  const callbackRef = { value: null as (() => void) | null }
  const mocks = {
    render: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
    setElementState: vi.fn().mockResolvedValue(undefined),
    focusElement: vi.fn().mockResolvedValue(undefined),
    on: vi.fn(),
    setSize: vi.fn(),
    setOptions: vi.fn(),
    zoomBy: vi.fn().mockResolvedValue(undefined),
    fitView: vi.fn().mockResolvedValue(undefined),
    layout: vi.fn().mockResolvedValue(undefined),
  }
  return { graphMocks: mocks, graphConstructorOptions: options, resizeObserverCallbackRef: callbackRef }
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
    resizeObserverCallbackRef.value = null

    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resizeObserverCallbackRef.value = callback
        }

        observe(): void {}

        disconnect(): void {}
      },
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('calls fitView after render on init', async () => {
    mount(PaperGraph, {
      props: { graph: sampleGraph },
      attachTo: document.body,
    })

    await flushPromises()

    expect(graphMocks.render).toHaveBeenCalledTimes(1)
    expect(graphMocks.fitView).toHaveBeenCalled()
    const renderOrder = graphMocks.render.mock.invocationCallOrder[0] ?? 0
    const fitViewOrder = graphMocks.fitView.mock.invocationCallOrder[0] ?? 0
    expect(renderOrder).toBeLessThan(fitViewOrder)
  })

  it('renders G6 graph from API graph payload', async () => {
    mount(PaperGraph, {
      props: { graph: sampleGraph },
      attachTo: document.body,
    })

    await flushPromises()

    expect(graphMocks.render).toHaveBeenCalled()
    expect(graphConstructorOptions.value?.padding).toBe(GRAPH_FIT_VIEW_PADDING_DEFAULT)
    expect(graphMocks.setOptions).toHaveBeenCalledWith({ padding: GRAPH_FIT_VIEW_PADDING_DEFAULT })
    expect(graphMocks.fitView).toHaveBeenCalled()
    expect(graphMocks.on).toHaveBeenCalled()
  })

  it('uses compact layout spacing and legend-aware fitView padding', async () => {
    mount(PaperGraph, {
      props: { graph: sampleGraph, compact: true },
      attachTo: document.body,
    })

    await flushPromises()

    const layout = graphConstructorOptions.value?.layout as ReturnType<typeof buildG6LayoutOptions>
    expect(layout).toEqual(buildG6LayoutOptions({ compact: true, nodeCount: sampleGraph.nodes.length }))
    expect(graphConstructorOptions.value?.padding).toEqual(GRAPH_FIT_VIEW_PADDING_COMPACT)
    expect(graphMocks.setOptions).toHaveBeenCalledWith({ padding: GRAPH_FIT_VIEW_PADDING_COMPACT })
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
    expect(nodeOptions?.animation?.update?.[0]?.fields).toEqual(['stroke', 'lineWidth', 'fill'])
    expect(nodeOptions?.animation?.update?.[0]?.fields).not.toContain('x')

    const behaviors = options?.behaviors as Array<string | { type?: string; state?: string }>
    expect(
      behaviors.some((item) => typeof item === 'object' && item.type === 'hover-activate' && item.state === 'hover'),
    ).toBe(true)

    const edgeOptions = options?.edge as { style?: { stroke?: string; lineWidth?: number } }
    expect(edgeOptions?.style?.stroke).toBe(GRAPH_EDGE_STROKE)
    expect(edgeOptions?.style?.lineWidth).toBe(1)
  })

  it('applies active highlight without stealing viewport in compact preview', async () => {
    const wrapper = mount(PaperGraph, {
      props: { graph: sampleGraph, compact: true, highlightNodeId: null },
      attachTo: document.body,
    })

    await flushPromises()
    graphMocks.setElementState.mockClear()
    graphMocks.focusElement.mockClear()

    await wrapper.setProps({ highlightNodeId: 'n2' })
    await flushPromises()

    expect(graphMocks.setElementState).toHaveBeenCalledWith({
      n1: [],
      n2: 'active',
    })
    expect(graphMocks.focusElement).not.toHaveBeenCalled()
  })

  it('focuses highlighted node only on full-bleed graph page', async () => {
    const wrapper = mount(PaperGraph, {
      props: { graph: sampleGraph, fullBleed: true, highlightNodeId: null },
      attachTo: document.body,
    })

    await flushPromises()
    graphMocks.focusElement.mockClear()

    await wrapper.setProps({ highlightNodeId: 'n2' })
    await flushPromises()

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

  describe('§17 viewport height conventions', () => {
    it('initializes G6 with GRAPH_DEFAULT_HEIGHT (480px) in default mode', async () => {
      mount(PaperGraph, {
        props: { graph: sampleGraph },
        attachTo: document.body,
      })

      await flushPromises()

      expect(graphConstructorOptions.value?.height).toBe(GRAPH_DEFAULT_HEIGHT)
      expect(GRAPH_DEFAULT_HEIGHT).toBe(480)
    })

    it('initializes G6 with GRAPH_COMPACT_HEIGHT (320px) in compact mode', async () => {
      mount(PaperGraph, {
        props: { graph: sampleGraph, compact: true },
        attachTo: document.body,
      })

      await flushPromises()

      expect(graphConstructorOptions.value?.height).toBe(GRAPH_COMPACT_HEIGHT)
      expect(GRAPH_COMPACT_HEIGHT).toBe(320)
    })

    it('initializes fullBleed G6 height at least GRAPH_FULL_MIN_HEIGHT (720px)', async () => {
      mount(PaperGraph, {
        props: { graph: sampleGraph, fullBleed: true },
        attachTo: document.body,
      })

      await flushPromises()

      expect(graphConstructorOptions.value?.height).toBeGreaterThanOrEqual(GRAPH_FULL_MIN_HEIGHT)
      expect(GRAPH_FULL_MIN_HEIGHT).toBe(720)
    })

    it('resizes G6 canvas via ResizeObserver using default height', async () => {
      vi.useFakeTimers()

      const wrapper = mount(PaperGraph, {
        props: { graph: sampleGraph },
        attachTo: document.body,
      })

      await flushPromises()
      graphMocks.setSize.mockClear()
      graphMocks.setOptions.mockClear()
      graphMocks.fitView.mockClear()

      const host = wrapper.find('.graph-host').element as HTMLDivElement
      Object.defineProperty(host, 'clientWidth', { configurable: true, value: 1024 })
      Object.defineProperty(host, 'clientHeight', { configurable: true, value: 600 })

      resizeObserverCallbackRef.value?.()

      expect(graphMocks.setSize).toHaveBeenCalledWith(1024, GRAPH_DEFAULT_HEIGHT)
      expect(graphMocks.fitView).not.toHaveBeenCalled()

      vi.advanceTimersByTime(GRAPH_FIT_VIEW_DEBOUNCE_MS)
      await flushPromises()

      expect(graphMocks.setOptions).toHaveBeenCalledWith({ padding: GRAPH_FIT_VIEW_PADDING_DEFAULT })
      expect(graphMocks.fitView).toHaveBeenCalled()

      vi.useRealTimers()
    })

    it('fullBleed resize uses max(container height, GRAPH_FULL_MIN_HEIGHT)', async () => {
      const wrapper = mount(PaperGraph, {
        props: { graph: sampleGraph, fullBleed: true },
        attachTo: document.body,
      })

      await flushPromises()
      graphMocks.setSize.mockClear()

      const host = wrapper.find('.graph-host').element as HTMLDivElement
      Object.defineProperty(host, 'clientWidth', { configurable: true, value: 800 })
      Object.defineProperty(host, 'clientHeight', { configurable: true, value: 900 })

      resizeObserverCallbackRef.value?.()

      expect(graphMocks.setSize).toHaveBeenCalledWith(800, 900)

      graphMocks.setSize.mockClear()
      Object.defineProperty(host, 'clientHeight', { configurable: true, value: 500 })
      resizeObserverCallbackRef.value?.()

      expect(graphMocks.setSize).toHaveBeenCalledWith(800, GRAPH_FULL_MIN_HEIGHT)
    })
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
    expect(graphMocks.setOptions).toHaveBeenCalledWith({ padding: GRAPH_FIT_VIEW_PADDING_DEFAULT })
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
