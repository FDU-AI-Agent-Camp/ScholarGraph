import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HomeView from '@/views/HomeView.vue'
import { readFrontendSource } from '@/test/helpers/designTokens'

const homeViewSrc = readFrontendSource('views/HomeView.vue')

const globalStubs = {
  HomeGraphMock: { template: '<div class="home-graph-mock-stub" />' },
  BadgeParadigm: {
    props: ['paradigm'],
    template: '<span class="badge-paradigm-stub" :data-paradigm="paradigm"><slot /></span>',
  },
  'el-button': { template: '<button class="el-button-stub"><slot /></button>' },
  'el-icon': true,
  'router-link': {
    props: ['to'],
    template: '<a class="router-link-stub" :href="String(to)"><slot /></a>',
  },
}

describe('HomeView', () => {
  it('defines 58/42 hero grid, page-content max-width, and padding-top 48 in layout styles', () => {
    expect(homeViewSrc).toContain('page-content')
    expect(homeViewSrc).toContain('padding-top: var(--spacing-48)')
    expect(homeViewSrc).toContain('grid-template-columns: 58fr 42fr')
  })

  it('renders baseline eyebrow, serif display title, and subtitle copy', () => {
    const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

    expect(wrapper.find('.home-eyebrow').text()).toBe('AI AGENT · GRAPH RAG')
    expect(wrapper.find('.home-title').classes()).toContain('text-display')
    expect(wrapper.findAll('.home-title-line').map((node) => node.text())).toEqual(['解构论文逻辑，', '发现学术共同体'])
    expect(wrapper.find('.home-subtitle').text()).toContain('人文社科')
    expect(wrapper.find('.home-subtitle').text()).toContain('理工科')
    expect(wrapper.find('.home-subtitle').classes()).toContain('text-body-lg')
  })

  it('renders primary and ghost CTAs linking to papers', () => {
    const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

    const buttons = wrapper.findAll('button')
    expect(buttons.some((button) => button.text() === '上传论文')).toBe(true)
    expect(buttons.some((button) => button.text() === '浏览文献库')).toBe(true)
    expect(
      wrapper.findAll('.router-link-stub').filter((link) => link.attributes('href') === '/papers').length,
    ).toBeGreaterThanOrEqual(2)
  })

  it('renders three workflow steps with primary-light icon circles', () => {
    const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

    const steps = wrapper.findAll('.home-step')
    expect(steps).toHaveLength(3)
    expect(steps.map((step) => step.find('.home-step-label').text())).toEqual(['上传 PDF', '自动建图', '问答·巡检'])
    expect(wrapper.findAll('.home-step-icon')).toHaveLength(3)
    expect(homeViewSrc).toContain('width: 40px')
    expect(homeViewSrc).toContain('height: 40px')
    expect(homeViewSrc).toContain('gap: var(--spacing-32)')
    expect(homeViewSrc).toContain('background: var(--color-primary-light)')
  })

  it('renders HSS/STEM badges with one-line paradigm caption', () => {
    const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

    const badges = wrapper.findAll('.badge-paradigm-stub')
    expect(badges.map((badge) => badge.attributes('data-paradigm'))).toEqual(['HSS', 'STEM'])
    expect(wrapper.find('.home-paradigms-caption').text()).toContain('人文社科')
    expect(wrapper.find('.home-paradigms-caption').text()).toContain('理工科')
  })

  it('embeds graph mock in the hero visual column', () => {
    const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

    expect(wrapper.find('.home-graph-mock-stub').exists()).toBe(true)
  })

  it('renders 60/40 quick-link cards with hover motion tokens', () => {
    expect(homeViewSrc).toContain('grid-template-columns: 60fr 40fr')
    expect(homeViewSrc).toContain('margin-top: var(--spacing-64)')
    expect(homeViewSrc).toContain('box-shadow: var(--shadow-md)')
    expect(homeViewSrc).toContain('border-color: var(--color-primary-muted)')
    expect(homeViewSrc).toContain('box-shadow var(--transition-instant)')

    const wrapper = mount(HomeView, { global: { stubs: globalStubs } })
    expect(wrapper.find('.home-quick-links').exists()).toBe(true)
    expect(wrapper.findAll('.home-quick-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('查看巡检演示')
    expect(wrapper.text()).toContain('打开示例论文')

    const patrolLink = wrapper.findAll('.router-link-stub').find((link) => link.attributes('href') === '/patrol')
    const detailLink = wrapper
      .findAll('.router-link-stub')
      .find((link) => link.attributes('href') === '/papers/hss-001')
    expect(patrolLink).toBeTruthy()
    expect(detailLink).toBeTruthy()
  })
})
