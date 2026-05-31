import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import BadgeStatus from '@/components/ui/BadgeStatus.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { EMPTY_STATE_PRESETS } from '@/components/ui/emptyStatePresets'
import InsightCard from '@/components/ui/InsightCard.vue'
import TagCitation from '@/components/ui/TagCitation.vue'
import { readFrontendSource } from '@/test/helpers/designTokens'

describe('BadgeParadigm', () => {
  it('renders HSS and STEM with text labels and token colors', () => {
    const hss = mount(BadgeParadigm, { props: { paradigm: 'HSS' } })
    const stem = mount(BadgeParadigm, { props: { paradigm: 'STEM' } })

    expect(hss.text()).toBe('HSS')
    expect(hss.classes()).toContain('badge-paradigm--HSS')
    expect(stem.text()).toBe('STEM')
    expect(stem.classes()).toContain('badge-paradigm--STEM')
  })

  it('falls back to unknown label for missing paradigm', () => {
    const wrapper = mount(BadgeParadigm, { props: { paradigm: null } })

    expect(wrapper.text()).toBe('未知')
    expect(wrapper.classes()).toContain('badge-paradigm--unknown')
  })
})

describe('BadgeStatus', () => {
  it('renders status dot and localized label for each variant', () => {
    const ready = mount(BadgeStatus, { props: { status: 'ready' } })

    expect(ready.find('.badge-status__dot').exists()).toBe(true)
    expect(ready.text()).toContain('已就绪')
    expect(ready.classes()).toContain('badge-status--ready')
  })

  it('applies processing pulse class hook', () => {
    const wrapper = mount(BadgeStatus, { props: { status: 'processing' } })

    expect(wrapper.classes()).toContain('badge-status--processing')
    expect(wrapper.text()).toContain('解构中')
  })
})

describe('TagCitation', () => {
  it('renders label and mono node id', () => {
    const wrapper = mount(TagCitation, {
      props: { label: '核心论点', nodeId: 'n1' },
    })

    expect(wrapper.find('.tag-citation__label').text()).toBe('核心论点')
    expect(wrapper.find('.tag-citation__node-id').text()).toBe('(n1)')
  })

  it('uses active variant class and emits click', async () => {
    const wrapper = mount(TagCitation, {
      props: { label: '核心论点', nodeId: 'n1', active: true },
    })

    expect(wrapper.classes()).toContain('tag-citation--active')
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('exposes citation-tag class for detail view integration', () => {
    const wrapper = mount(TagCitation, {
      props: { label: '核心论点', nodeId: 'n1' },
    })

    expect(wrapper.classes()).toContain('citation-tag')
    expect(wrapper.classes()).toContain('tag-citation')
  })

  it('uses 120ms instant transition on default hover states', () => {
    const src = readFrontendSource('components/ui/TagCitation.vue')
    expect(src).toContain('var(--transition-instant)')
    expect(src).not.toMatch(/transition:\s*all/i)
  })
})

describe('EmptyState', () => {
  it('uses preset copy for no-papers variant', () => {
    const wrapper = mount(EmptyState, { props: { variant: 'no-papers' } })

    expect(wrapper.find('.empty-state__title').text()).toBe(EMPTY_STATE_PRESETS['no-papers'].title)
    expect(wrapper.find('.empty-state__body').text()).toBe(EMPTY_STATE_PRESETS['no-papers'].description)
  })

  it('allows title and action slot overrides', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '自定义标题', description: '自定义说明' },
      slots: {
        action: '<button class="cta">上传</button>',
      },
    })

    expect(wrapper.find('.empty-state__title').text()).toBe('自定义标题')
    expect(wrapper.find('.empty-state__body').text()).toBe('自定义说明')
    expect(wrapper.find('.cta').exists()).toBe(true)
  })
})

describe('InsightCard', () => {
  it('renders lens_clash left accent border variant', () => {
    const wrapper = mount(InsightCard, {
      props: {
        variant: 'lens_clash',
        title: '视角冲突',
        insightId: 'ins-1',
        summary: '摘要内容',
      },
    })

    expect(wrapper.classes()).toContain('insight-card--lens_clash')
    expect(wrapper.find('.insight-card__title').text()).toBe('视角冲突')
    expect(wrapper.find('.insight-card__id').text()).toBe('ins-1')
    expect(wrapper.find('.insight-card__summary').text()).toBe('摘要内容')
  })

  it('renders contradiction variant and default slot', () => {
    const wrapper = mount(InsightCard, {
      props: { variant: 'contradiction', title: '论点矛盾' },
      slots: { default: '<p class="refs">node refs</p>' },
    })

    expect(wrapper.classes()).toContain('insight-card--contradiction')
    expect(wrapper.find('.refs').exists()).toBe(true)
  })
})
