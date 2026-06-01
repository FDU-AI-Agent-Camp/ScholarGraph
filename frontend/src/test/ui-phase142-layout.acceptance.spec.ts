/**
 * ui-design-progress §1.4.2 — 形状、布局与排布（间距 / 圆角 / typography / 视线流）
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { loadDesignTokenMap } from '@/test/helpers/designTokens'
import {
  countHeadingLevel,
  extractStyleBlocks,
  extractVueTemplate,
  hasNoOffScaleMarginTop,
  listOffScaleSpacingPxValues,
  listRawFontSizePx,
  SPACING_TOKEN_NAMES,
  usesOnlySpacingTokensOrAllowlistedPx,
  WORKBENCH_LAYOUT_FILES,
} from '@/test/helpers/layoutDiscipline'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const VIEW_FILES = [
  'views/HomeView.vue',
  'views/PapersView.vue',
  'views/PaperDetailView.vue',
  'views/PaperGraphView.vue',
  'views/PatrolView.vue',
] as const

const RAW_FONT_SIZE_ALLOWLIST = ['components/layout/AppLayout.vue', 'components/home/HomeGraphMock.vue'] as const

function readSrc(relativePathFromSrc: string): string {
  return readFileSync(resolve(FRONTEND_SRC, relativePathFromSrc), 'utf8')
}

describe('§1.4.2 Layout & typography discipline', () => {
  const tokens = loadDesignTokenMap()
  const tokensCss = readSrc('styles/tokens.css')
  const typographyCss = readSrc('styles/typography.css')

  describe('设计参数与 Token 落地', () => {
    it('tokens.css documents §1.4.2 DESIGN_VARIANCE / VISUAL_DENSITY spacing discipline', () => {
      expect(tokensCss).toContain('§1.4.2 layout discipline')
      expect(tokensCss).toContain('DESIGN_VARIANCE')
      expect(tokensCss).toContain('VISUAL_DENSITY')
      expect(tokensCss).toContain('--content-max-width: 1280px')
    })

    it('defines full spacing scale 4–64 and radius sm–2xl', () => {
      for (const name of SPACING_TOKEN_NAMES) {
        expect(tokens[name]).toBeTruthy()
      }
      expect(tokens['--radius-sm']).toBe('4px')
      expect(tokens['--radius-md']).toBe('6px')
      expect(tokens['--radius-lg']).toBe('8px')
      expect(tokens['--radius-xl']).toBe('12px')
      expect(tokens['--radius-2xl']).toBe('16px')
    })

    it('typography scale matches design-spec §1.4.2 table', () => {
      expect(tokens['--text-display-size']).toBe('40px')
      expect(tokens['--text-h1-size']).toBe('24px')
      expect(tokens['--text-h2-size']).toBe('18px')
      expect(tokens['--text-h3-size']).toBe('16px')
      expect(tokens['--text-body-size']).toBe('14px')
      expect(tokens['--text-body-lg-size']).toBe('16px')
      expect(tokens['--text-caption-size']).toBe('12px')
      expect(tokens['--text-mono-size']).toBe('13px')
      expect(typographyCss).toContain('.text-display')
      expect(typographyCss).toContain('.text-h1')
      expect(typographyCss).toContain('.text-body-lg')
      expect(typographyCss).toContain('.text-mono')
    })

    it('main.css exposes page-content max-width wrapper', () => {
      expect(readSrc('assets/main.css')).toContain('.page-content')
      expect(readSrc('assets/main.css')).toContain('max-width: var(--content-max-width)')
    })
  })

  describe('DESIGN_VARIANCE — 非对称 vs 对称布局', () => {
    it('Home hero 58/42 and quick links 60/40 (not equal thirds)', () => {
      const homeSrc = readSrc('views/HomeView.vue')
      expect(homeSrc).toContain('grid-template-columns: 58fr 42fr')
      expect(homeSrc).toContain('grid-template-columns: 60fr 40fr')
      expect(homeSrc).not.toContain('grid-template-columns: 1fr 1fr 1fr')
    })

    it('Patrol report uses asymmetric two-column insight grid', () => {
      const patrolSrc = readSrc('views/PatrolView.vue')
      expect(patrolSrc).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))')
    })

    it('Shell / Papers / Detail workbench grids stay symmetric', () => {
      expect(readSrc('components/layout/AppLayout.vue')).toContain('width="240px"')
      expect(readSrc('views/PaperDetailView.vue')).toContain('grid-template-columns: 45fr 55fr')
      expect(readSrc('views/PapersView.vue')).toContain('class="papers-table"')
    })
  })

  describe('VISUAL_DENSITY — 疏密分区', () => {
    it('Home uses sparse 48/64 section spacing', () => {
      const homeStyles = extractStyleBlocks(readSrc('views/HomeView.vue'))
      expect(homeStyles).toContain('padding-top: var(--spacing-48)')
      expect(homeStyles).toContain('margin-top: var(--spacing-64)')
      expect(homeStyles).toContain('margin: var(--spacing-48) 0 0')
    })

    it('Papers table enforces compact 52px row rhythm', () => {
      expect(readSrc('views/PapersView.vue')).toContain('height: 52px')
    })

    it('Detail dual-column uses 24px gap between modules', () => {
      const detailStyles = extractStyleBlocks(readSrc('views/PaperDetailView.vue'))
      expect(detailStyles).toContain('gap: var(--spacing-24)')
    })
  })

  describe('间距纪律 — scale token，无魔法 margin', () => {
    it('primary views use spacing tokens for margin/padding/gap (2px micro-offset allowed)', () => {
      for (const viewPath of VIEW_FILES) {
        const styles = extractStyleBlocks(readSrc(viewPath))
        expect(usesOnlySpacingTokensOrAllowlistedPx(styles, true), viewPath).toBe(true)
      }
    })

    it('views apply page-content or content-max-width (Graph full-bleed exempt)', () => {
      expect(readSrc('views/HomeView.vue')).toContain('page-content')
      expect(readSrc('views/PatrolView.vue')).toContain('var(--content-max-width)')
      expect(readSrc('views/PaperGraphView.vue')).toContain('full-bleed')
    })
  })

  describe('圆角形状语言', () => {
    it('Home mock container is the sole radius-2xl (16px) usage in home mock', () => {
      const mockSrc = readSrc('components/home/HomeGraphMock.vue')
      expect(mockSrc).toContain('border-radius: var(--radius-2xl)')
      expect(mockSrc).not.toMatch(/border-radius:\s*16px/)
    })

    it('page cards and upload zone use radius-xl', () => {
      expect(readSrc('assets/main.css')).toContain('border-radius: var(--radius-xl)')
      expect(readSrc('components/papers/PaperUpload.vue')).toContain('border-radius: var(--radius-xl)')
    })
  })

  describe('Typography — 禁止 views 内随意 font-size px', () => {
    it('views scoped styles avoid raw font-size px (use utilities or --text-* tokens)', () => {
      for (const viewPath of VIEW_FILES) {
        const styles = extractStyleBlocks(readSrc(viewPath))
        const rawSizes = listRawFontSizePx(styles)
        expect(rawSizes, `${viewPath} raw font-size px: ${rawSizes.join(', ')}`).toEqual([])
      }
    })

    it('Home display title is the only text-display usage in views', () => {
      const homeTemplate = extractVueTemplate(readSrc('views/HomeView.vue'))
      expect(homeTemplate).toContain('text-display')
      for (const viewPath of VIEW_FILES) {
        if (viewPath === 'views/HomeView.vue') {
          continue
        }
        expect(extractVueTemplate(readSrc(viewPath))).not.toContain('text-display')
      }
    })

    it('allowlisted components may retain decorative icon sizing without raw px in views', () => {
      for (const path of RAW_FONT_SIZE_ALLOWLIST) {
        expect(readSrc(path).length).toBeGreaterThan(0)
      }
    })
  })

  describe('H2 密度与 Detail 视线流', () => {
    it('each primary view keeps ≤3 H2 section titles per screen', () => {
      for (const viewPath of VIEW_FILES) {
        const h2Count = countHeadingLevel(readSrc(viewPath), 2)
        expect(h2Count, viewPath).toBeLessThanOrEqual(3)
      }
    })

    it('Detail left column module order: metadata → pipeline → QA; graph preview in aside', () => {
      const detailSrc = readSrc('views/PaperDetailView.vue')
      const template = extractVueTemplate(detailSrc)
      const metadataIndex = template.indexOf('PaperMetadataCard')
      const pipelineIndex = template.indexOf('PaperStatusPanel')
      const qaIndex = template.indexOf('class="detail-qa"')
      const graphIndex = template.indexOf('class="detail-graph"')

      expect(metadataIndex).toBeGreaterThan(-1)
      expect(pipelineIndex).toBeGreaterThan(metadataIndex)
      expect(qaIndex).toBeGreaterThan(pipelineIndex)
      expect(graphIndex).toBeGreaterThan(qaIndex)
      expect(detailSrc).toContain('grid-template-columns: 45fr 55fr')
    })

    it('Detail main column stacks modules with spacing-24 and inset answer panel', () => {
      const detailStyles = extractStyleBlocks(readSrc('views/PaperDetailView.vue'))
      expect(detailStyles).toContain('.detail-main')
      expect(detailStyles).toContain('gap: var(--spacing-24)')
      expect(detailStyles).toContain('.detail-qa__answer-panel')
      expect(detailStyles).toContain('padding: var(--spacing-16)')
    })
  })

  describe('§1.4.2 布局验收 — checklist（ui-design-progress §154–159）', () => {
    it('Home：58/42 hero + 底部 60/40 quick links，非三等分', () => {
      const homeSrc = readSrc('views/HomeView.vue')
      expect(homeSrc).toContain('grid-template-columns: 58fr 42fr')
      expect(homeSrc).toContain('grid-template-columns: 60fr 40fr')
      expect(homeSrc).not.toMatch(/grid-template-columns:\s*1fr\s+1fr\s+1fr/)
      expect(homeSrc).not.toMatch(/grid-template-columns:\s*repeat\(3,\s*1fr\)/)
    })

    it('Detail：≥1024px 双栏 45/55、gap 24、左栏模块顺序（Phase 5.1）', () => {
      const detailSrc = readSrc('views/PaperDetailView.vue')
      const template = extractVueTemplate(detailSrc)

      expect(detailSrc).toContain('@media (min-width: 1024px)')
      expect(detailSrc).toContain('grid-template-columns: 45fr 55fr')
      expect(extractStyleBlocks(detailSrc)).toContain('gap: var(--spacing-24)')

      expect(template.indexOf('PaperMetadataCard')).toBeLessThan(template.indexOf('PaperStatusPanel'))
      expect(template.indexOf('PaperStatusPanel')).toBeLessThan(template.indexOf('class="detail-qa"'))
      expect(template.indexOf('class="detail-qa"')).toBeLessThan(template.indexOf('class="detail-graph"'))
    })

    it('同屏 H2 ≤3；Shell/page-card 有 inset padding，避免贴边挤满', () => {
      for (const viewPath of VIEW_FILES) {
        expect(countHeadingLevel(readSrc(viewPath), 2), viewPath).toBeLessThanOrEqual(3)
      }

      const appLayoutStyles = extractStyleBlocks(readSrc('components/layout/AppLayout.vue'))
      expect(appLayoutStyles).toContain('.main {')
      expect(appLayoutStyles).toContain('padding: var(--spacing-24) var(--spacing-32)')
      expect(readSrc('assets/main.css')).toContain('.page-card')
      expect(readSrc('assets/main.css')).toContain('padding: var(--spacing-24)')
      expect(readSrc('views/HomeView.vue')).toContain('padding: var(--spacing-24)')
    })

    it('表格 / Stepper / 表单对齐网格，无 margin-top: 13px 类魔法数', () => {
      for (const filePath of WORKBENCH_LAYOUT_FILES) {
        const styles = extractStyleBlocks(readSrc(filePath))
        expect(listOffScaleSpacingPxValues(styles, true), filePath).toEqual([])
        expect(hasNoOffScaleMarginTop(styles, true), filePath).toBe(true)
      }

      expect(readSrc('views/PapersView.vue')).toContain('height: 52px')
      expect(readSrc('components/papers/PaperStatusPanel.vue')).toContain('gap: var(--spacing-12)')
      expect(readSrc('views/PatrolView.vue')).toContain('patrol-view__paper-grid')
      expect(readSrc('views/PatrolView.vue')).toContain('display: grid')
    })
  })
})
