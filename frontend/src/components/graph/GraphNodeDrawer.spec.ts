/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type { GraphNode } from '@/api/types'
import GraphNodeDrawer from '@/components/graph/GraphNodeDrawer.vue'
import { GRAPH_BASELINE_COPY, GRAPH_DRAWER_WIDTH_PX } from '@/constants/graphCopy'
import { readFrontendSource } from '@/test/helpers/designTokens'

const sampleNode: GraphNode = {
  id: 'n1',
  label: '核心论点',
  type: 'Thesis',
  data: { snippet: '这是节点摘录。' },
}

describe('GraphNodeDrawer', () => {
  it('renders label, type badge, node id, and snippet fields', () => {
    const wrapper = mount(GraphNodeDrawer, {
      props: { modelValue: true, node: sampleNode },
      global: {
        stubs: {
          'el-drawer': {
            props: ['modelValue', 'size'],
            template: '<div class="el-drawer-stub" :data-size="size"><slot /></div>',
          },
        },
      },
    })

    expect(wrapper.find('.graph-node-drawer__label').text()).toBe('核心论点')
    expect(wrapper.find('.graph-node-drawer__type-badge').text()).toBe('Thesis')
    expect(wrapper.find('.graph-node-drawer__node-id').text()).toBe('n1')
    expect(wrapper.find('.graph-node-drawer__snippet').text()).toBe('这是节点摘录。')
    expect(wrapper.find('.el-drawer-stub').attributes('data-size')).toBe(`${GRAPH_DRAWER_WIDTH_PX}px`)
  })

  it('shows baseline empty snippet copy when node has no snippet', () => {
    const wrapper = mount(GraphNodeDrawer, {
      props: {
        modelValue: true,
        node: { id: 'n2', label: '分论点', type: 'SubArgument', data: {} },
      },
      global: {
        stubs: {
          'el-drawer': { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.find('.graph-node-drawer__snippet').text()).toBe(GRAPH_BASELINE_COPY.drawerNoSnippet)
    expect(wrapper.find('.graph-node-drawer__snippet').classes()).toContain('graph-node-drawer__snippet--empty')
  })

  it('uses 320px width and 250ms slide transition token', () => {
    const src = readFrontendSource('components/graph/GraphNodeDrawer.vue')

    expect(src).toContain('GRAPH_DRAWER_WIDTH_PX')
    expect(GRAPH_DRAWER_WIDTH_PX).toBe(320)
    expect(src).toContain('var(--transition-slow)')
  })

  it('copies node id to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const wrapper = mount(GraphNodeDrawer, {
      props: { modelValue: true, node: sampleNode },
      global: {
        stubs: {
          'el-drawer': { template: '<div><slot /></div>' },
        },
      },
    })

    await wrapper.find('.graph-node-drawer__copy').trigger('click')
    await Promise.resolve()

    expect(writeText).toHaveBeenCalledWith('n1')
    vi.unstubAllGlobals()
  })

  it('emits update:modelValue when close button is clicked', async () => {
    const wrapper = mount(GraphNodeDrawer, {
      props: { modelValue: true, node: sampleNode },
      global: {
        stubs: {
          'el-drawer': { template: '<div><slot /></div>' },
        },
      },
    })

    await wrapper.find('.graph-node-drawer__close').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})
