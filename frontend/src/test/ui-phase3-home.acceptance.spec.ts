/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Phase 3 Home acceptance — design-spec §7 + ui-design-progress §1.4.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HomeGraphMock from '@/components/home/HomeGraphMock.vue'
import HomeView from '@/views/HomeView.vue'
import { HOME_BASELINE_COPY } from '@/constants/homeCopy'
import { readFrontendSource } from '@/test/helpers/designTokens'

const homeViewSrc = readFrontendSource('views/HomeView.vue')
const graphMockSrc = readFrontendSource('components/home/HomeGraphMock.vue')

function readStyleBlock(source: string, selector: string): string {
  const escaped = selector.replace('.', '\\.')
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))
  return match?.[1] ?? ''
}

const globalStubs = {
  HomeGraphMock: { template: '<div class="home-graph-mock-stub" />' },
  BadgeParadigm: {
    props: ['paradigm'],
    template: '<span class="badge-paradigm-stub" :data-paradigm="paradigm" />',
  },
  'el-button': { template: '<button><slot /></button>' },
  'el-icon': true,
  'router-link': {
    props: ['to'],
    template: '<a class="router-link-stub" :href="String(to)"><slot /></a>',
  },
}

describe('Phase 3 Home acceptance', () => {
  describe('§1.4.2 asymmetric layout and 48/64 spacing', () => {
    it('uses 58/42 hero and 60/40 quick-link grids (DESIGN_VARIANCE high)', () => {
      expect(homeViewSrc).toContain('grid-template-columns: 58fr 42fr')
      expect(homeViewSrc).toContain('grid-template-columns: 60fr 40fr')
      expect(homeViewSrc).not.toMatch(/grid-template-columns:\s*repeat\(3/)
      expect(homeViewSrc).not.toContain('grid-template-columns: 1fr 1fr 1fr')
    })

    it('applies page-level spacing scale 48 and 64', () => {
      expect(homeViewSrc).toContain('padding-top: var(--spacing-48)')
      expect(homeViewSrc).toContain('margin: var(--spacing-48) 0 0')
      expect(homeViewSrc).toContain('margin-top: var(--spacing-64)')
    })

    it('mounts hero and quick sections without equal-width triple columns', () => {
      const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

      expect(wrapper.find('.home-hero').exists()).toBe(true)
      expect(wrapper.find('.home-quick-links').exists()).toBe(true)
      expect(wrapper.findAll('.home-quick-card')).toHaveLength(2)
      expect(wrapper.find('.home-copy').exists()).toBe(true)
      expect(wrapper.find('.home-visual').exists()).toBe(true)
    })
  })

  describe('§1.4.1 canvas background with surface float layers', () => {
    it('HomeGraphMock separates canvas base from surface nodes and insight cards', () => {
      expect(graphMockSrc).toContain('background: var(--color-bg-canvas)')
      expect(graphMockSrc).toContain('fill: var(--color-bg-surface)')
      expect(graphMockSrc).toContain('background: var(--color-bg-surface)')
      expect(graphMockSrc).toContain('box-shadow: var(--shadow-md)')

      const wrapper = mount(HomeGraphMock)
      expect(wrapper.find('.home-graph-mock__canvas').exists()).toBe(true)
      expect(wrapper.findAll('.home-graph-mock__node').length).toBeGreaterThan(0)
      expect(wrapper.findAll('.home-graph-mock__insight').length).toBe(2)
    })

    it('Home quick cards use surface tokens instead of full-page flat white', () => {
      expect(homeViewSrc).toContain('background: var(--color-bg-surface)')
      expect(homeViewSrc).toContain('box-shadow: var(--shadow-sm)')
      expect(homeViewSrc).not.toMatch(/\.home\s*\{[^}]*background:\s*#fff/i)
      expect(homeViewSrc).not.toMatch(/\.home\s*\{[^}]*background:\s*var\(--color-bg-surface\)/)
    })
  })

  describe('§1.4.4 baseline copy for hero and CTAs', () => {
    it('matches eyebrow, title lines, and CTA labels from baseline table', () => {
      const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

      expect(wrapper.find('.home-eyebrow').text()).toBe(HOME_BASELINE_COPY.eyebrow)
      expect(wrapper.findAll('.home-title-line').map((node) => node.text())).toEqual([...HOME_BASELINE_COPY.titleLines])

      const buttonLabels = wrapper.findAll('button').map((button) => button.text())
      expect(buttonLabels).toContain(HOME_BASELINE_COPY.primaryCta)
      expect(buttonLabels).toContain(HOME_BASELINE_COPY.secondaryCta)
    })

    it('keeps subtitle within body-lg secondary treatment and max-width 480', () => {
      expect(homeViewSrc).toContain('max-width: 480px')
      expect(homeViewSrc).toMatch(/\.home-subtitle[\s\S]*color: var\(--color-text-secondary\)/)

      const wrapper = mount(HomeView, { global: { stubs: globalStubs } })
      expect(wrapper.find('.home-subtitle').classes()).toContain('text-body-lg')
      expect(wrapper.find('.home-subtitle').text()).toMatch(/人文社科.*理工科|理工科.*人文社科/)
    })
  })

  describe('anti-pattern: no centered Hero + three equal cards', () => {
    it('avoids centered hero layout and three-column card grids', () => {
      expect(readStyleBlock(homeViewSrc, '.home-copy')).not.toContain('text-align')
      expect(readStyleBlock(homeViewSrc, '.home-title')).not.toContain('text-align')
      expect(readStyleBlock(homeViewSrc, '.home-eyebrow')).not.toContain('text-align')
      expect(homeViewSrc).not.toContain('repeat(3')
      expect(homeViewSrc).not.toContain('33.33%')

      const wrapper = mount(HomeView, { global: { stubs: globalStubs } })
      expect(wrapper.findAll('.home-quick-card')).toHaveLength(2)
      expect(wrapper.find('.text-display').exists()).toBe(true)
    })

    it('does not use legacy scaffold placeholder copy', () => {
      const wrapper = mount(HomeView, { global: { stubs: globalStubs } })

      expect(wrapper.text()).not.toContain('前后端通用骨架')
      expect(wrapper.text()).not.toContain('ScholarGraph 工作台')
      expect(wrapper.text()).not.toContain('本地联调')
    })
  })
})
