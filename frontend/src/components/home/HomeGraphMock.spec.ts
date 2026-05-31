import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HomeGraphMock from '@/components/home/HomeGraphMock.vue'
import { readFrontendSource } from '@/test/helpers/designTokens'

const mockSrc = readFrontendSource('components/home/HomeGraphMock.vue')

describe('HomeGraphMock', () => {
  it('uses 520x420 canvas container with graph nodes and insight float cards', () => {
    const wrapper = mount(HomeGraphMock)

    expect(mockSrc).toContain('max-width: 520px')
    expect(mockSrc).toContain('height: 420px')
    expect(mockSrc).toContain('background: var(--color-bg-canvas)')
    expect(wrapper.find('.home-graph-mock__canvas').exists()).toBe(true)
    expect(wrapper.findAll('.home-graph-mock__node').length).toBeGreaterThanOrEqual(6)
    expect(wrapper.findAll('.home-graph-mock__insight')).toHaveLength(2)
    expect(mockSrc).toContain('box-shadow: var(--shadow-md)')
  })
})
