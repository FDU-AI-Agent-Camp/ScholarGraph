/**
 * Phase 2 shared UI acceptance — design-spec §12 + ui-design-progress §1.4.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import { PARADIGM_LABELS } from '@/utils/paradigmLabels'
import BadgeStatus from '@/components/ui/BadgeStatus.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { EMPTY_STATE_PRESETS } from '@/components/ui/emptyStatePresets'
import TagCitation from '@/components/ui/TagCitation.vue'
import type { PaperStatus } from '@/api/types'
import { cssToken } from '@/utils/cssTokens'
import { DESIGN_SPEC_SEMANTIC_COLORS, loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'

/** ui-design-progress §1.4.4 baseline table (Papers Empty + Phase 2 presets). */
const EMPTY_BASELINE_COPY = {
  'no-papers': {
    title: '还没有论文',
    description: '上传 PDF 开始自动解构',
  },
  'no-graph': {
    title: '暂无图谱',
    description: '论文 ready 后将展示逻辑图谱预览',
  },
  'no-report': {
    title: '还没有巡检报告',
    description: '选择两篇 ready 论文并运行巡检',
  },
} as const

describe('Phase 2 UI acceptance', () => {
  describe('§1.4.1 Badge semantic colors and text labels', () => {
    const tokens = loadDesignTokenMap()
    const badgeParadigmSrc = readFrontendSource('components/ui/BadgeParadigm.vue')
    const badgeStatusSrc = readFrontendSource('components/ui/BadgeStatus.vue')

    it('tokens.css carries design-spec HSS/STEM and status semantic hex', () => {
      expect(tokens['--color-hss-bg']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.hssBg)
      expect(tokens['--color-hss-text']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.hssText)
      expect(tokens['--color-stem-bg']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.stemBg)
      expect(tokens['--color-stem-text']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.stemText)
      expect(tokens['--color-success']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.success)
      expect(tokens['--color-error']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.error)
      expect(tokens['--color-info']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.info)
      expect(tokens['--color-text-muted']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.textMuted)
    })

    it('BadgeParadigm maps variants to token vars (not hard-coded hex)', () => {
      expect(badgeParadigmSrc).toContain('var(--color-hss-bg)')
      expect(badgeParadigmSrc).toContain('var(--color-hss-text)')
      expect(badgeParadigmSrc).toContain('var(--color-stem-bg)')
      expect(badgeParadigmSrc).toContain('var(--color-stem-text)')
      expect(badgeParadigmSrc).not.toMatch(/#[0-9a-f]{3,8}/i)
    })

    it('BadgeStatus dot colors bind to semantic tokens', () => {
      expect(badgeStatusSrc).toContain('var(--color-text-muted)')
      expect(badgeStatusSrc).toContain('var(--color-info)')
      expect(badgeStatusSrc).toContain('var(--color-success)')
      expect(badgeStatusSrc).toContain('var(--color-error)')
    })

    it('renders HSS/STEM/unknown with visible Chinese text labels', () => {
      expect(mount(BadgeParadigm, { props: { paradigm: 'HSS' } }).text()).toBe(PARADIGM_LABELS.HSS)
      expect(mount(BadgeParadigm, { props: { paradigm: 'STEM' } }).text()).toBe(PARADIGM_LABELS.STEM)
      expect(mount(BadgeParadigm, { props: { paradigm: undefined } }).text()).toBe('未知')
    })

    it('covers all PaperStatus variants with dot + label', () => {
      const statuses: PaperStatus[] = [
        'pending',
        'processing',
        'indexing',
        'ready',
        'ready_with_warnings',
        'failed',
      ]
      for (const status of statuses) {
        const wrapper = mount(BadgeStatus, { props: { status } })
        expect(wrapper.find('.badge-status__dot').exists()).toBe(true)
        expect(wrapper.find('.badge-status__label').text().length).toBeGreaterThan(0)
        expect(wrapper.classes()).toContain(`badge-status--${status}`)
      }
    })
  })

  describe('TagCitation active color matches Graph active (#E11D48)', () => {
    const tokens = loadDesignTokenMap()
    const tagSrc = readFrontendSource('components/ui/TagCitation.vue')
    const graphSrc = readFrontendSource('components/graph/PaperGraph.vue')

    it('citation active token is #e11d48 in tokens.css', () => {
      expect(tokens['--color-citation-active']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.citationActive)
      expect(tokens['--color-citation-active-text']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.citationActiveText)
      expect(tokens['--color-citation-active-bg']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.citationActiveBg)
    })

    it('TagCitation active state uses citation active tokens', () => {
      expect(tagSrc).toContain('var(--color-citation-active)')
      expect(tagSrc).toContain('var(--color-citation-active-bg)')
      expect(tagSrc).toContain('var(--color-citation-active-text)')
    })

    it('PaperGraph active stroke reads the same citation active token', () => {
      const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')
      expect(paperGraphUtilSrc).toContain("'--color-citation-active'")
      expect(paperGraphUtilSrc).toContain("'--color-citation-active-bg'")
      expect(graphSrc).toContain('resolvePaperGraphThemeTokens')
    })

    it('cssToken resolves citation active to #e11d48 with tokens.css loaded', () => {
      expect(cssToken('--color-citation-active', '#e11d48')).toBe('#e11d48')
      expect(cssToken('--color-citation-active', '#e11d48')).toBe(tokens['--color-citation-active'])
    })

    it('mounts active TagCitation with active modifier class', () => {
      const wrapper = mount(TagCitation, {
        props: { label: '核心论点', nodeId: 'n1', active: true },
      })
      expect(wrapper.find('.tag-citation').classes()).toContain('tag-citation--active')
    })
  })

  describe('EmptyState §1.4.4 baseline copy and overrides', () => {
    it('presets match baseline table for all variants', () => {
      for (const variant of ['no-papers', 'no-graph', 'no-report'] as const) {
        expect(EMPTY_STATE_PRESETS[variant].title).toBe(EMPTY_BASELINE_COPY[variant].title)
        expect(EMPTY_STATE_PRESETS[variant].description).toBe(EMPTY_BASELINE_COPY[variant].description)
      }
    })

    it('renders baseline no-papers copy by default', () => {
      const wrapper = mount(EmptyState, { props: { variant: 'no-papers' } })
      expect(wrapper.find('.empty-state__title').text()).toBe('还没有论文')
      expect(wrapper.find('.empty-state__body').text()).toBe('上传 PDF 开始自动解构')
    })

    it('allows prop overrides for title and description', () => {
      const wrapper = mount(EmptyState, {
        props: { variant: 'no-papers', title: '自定义标题', description: '自定义正文' },
      })
      expect(wrapper.find('.empty-state__title').text()).toBe('自定义标题')
      expect(wrapper.find('.empty-state__body').text()).toBe('自定义正文')
    })

    it('allows body and action slot overrides', () => {
      const wrapper = mount(EmptyState, {
        props: { variant: 'no-papers' },
        slots: {
          body: '<span class="custom-body">slot 正文</span>',
          action: '<button class="custom-action">去上传</button>',
        },
      })
      expect(wrapper.find('.custom-body').text()).toBe('slot 正文')
      expect(wrapper.find('.custom-action').text()).toBe('去上传')
    })
  })

  describe('§1.4.3 interactive hover 120ms (no transition: all)', () => {
    const tokens = loadDesignTokenMap()
    const tagSrc = readFrontendSource('components/ui/TagCitation.vue')

    it('motion tokens define 120ms instant duration', () => {
      expect(tokens['--duration-instant']).toBe('120ms')
      expect(tokens['--transition-instant']).toContain('var(--duration-instant)')
      expect(tokens['--ease-out-product']).toContain('cubic-bezier')
    })

    it('TagCitation hover uses --transition-instant on explicit properties', () => {
      expect(tagSrc).toContain('var(--transition-instant)')
      expect(tagSrc).toMatch(/background-color var\(--transition-instant\)/)
      expect(tagSrc).not.toMatch(/transition:\s*all/i)
    })

    it('TagCitation active sync uses 150ms --transition-fast', () => {
      expect(tagSrc).toContain('var(--transition-fast)')
      expect(tokens['--duration-fast']).toBe('150ms')
    })
  })
})
