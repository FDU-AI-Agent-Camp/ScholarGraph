import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { readFrontendSource } from '@/test/helpers/designTokens'

const globalStubs = {
  'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
}

describe('GraphToolbar', () => {
  it('renders zoom/fit controls and disabled search placeholder', () => {
    const wrapper = mount(GraphToolbar, { global: { stubs: globalStubs } })

    expect(wrapper.find('.graph-toolbar').exists()).toBe(true)
    expect(wrapper.findAll('.graph-toolbar__button')).toHaveLength(4)
    expect((wrapper.find('.graph-toolbar__search-input').element as HTMLInputElement).placeholder).toBe(
      GRAPH_BASELINE_COPY.toolbarSearchPlaceholder,
    )
  })

  it('uses surface background, shadow-md, and 120ms button hover transitions', () => {
    const src = readFrontendSource('components/graph/GraphToolbar.vue')

    expect(src).toContain('var(--color-bg-surface)')
    expect(src).toContain('var(--shadow-md)')
    expect(src).toContain('var(--transition-instant)')
    expect(src).not.toMatch(/transition:\s*all/i)
  })

  it('emits toolbar actions', async () => {
    const wrapper = mount(GraphToolbar, { global: { stubs: globalStubs } })
    const buttons = wrapper.findAll('.graph-toolbar__button')

    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')
    await buttons[2]?.trigger('click')
    await buttons[3]?.trigger('click')

    expect(wrapper.emitted('zoomIn')).toHaveLength(1)
    expect(wrapper.emitted('zoomOut')).toHaveLength(1)
    expect(wrapper.emitted('fitView')).toHaveLength(1)
    expect(wrapper.emitted('resetLayout')).toHaveLength(1)
  })

  it('disables toolbar buttons when disabled prop is true', async () => {
    const wrapper = mount(GraphToolbar, {
      props: { disabled: true },
      global: { stubs: globalStubs },
    })

    for (const button of wrapper.findAll('.graph-toolbar__button')) {
      expect((button.element as HTMLButtonElement).disabled).toBe(true)
    }

    await wrapper.find('.graph-toolbar__button').trigger('click')
    expect(wrapper.emitted('zoomIn')).toBeUndefined()
  })
})
