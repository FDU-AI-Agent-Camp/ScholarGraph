/**
 * ui-design-progress §9 — 体验质量 × Phase 对照表 + 总验收（Phase 8 全表复核）。
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { EMPTY_STATE_PRESETS } from '@/components/ui/emptyStatePresets'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { PIPELINE_STEPS } from '@/utils/pipelineSteps'
import { GRAPH_STATE_ANIMATION_MS } from '@/utils/paperGraph'
import { contrastRatio, WCAG_AA_TEXT_CONTRAST, WCAG_AA_UI_CONTRAST } from '@/test/helpers/colorContrast'
import { loadDesignTokenMap } from '@/test/helpers/designTokens'
import { countHeadingLevel } from '@/test/helpers/layoutDiscipline'
import { getGraphNodeFillColor, listGraphNodeTypeStrokeColors, GRAPH_NODE_SURFACE_FILL } from '@/utils/paperGraph'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const FRONTEND_ROOT = resolve(FRONTEND_SRC, '..')

const PHASE_ACCEPTANCE_FILES = [
  'test/ui-phase2.acceptance.spec.ts',
  'test/ui-phase3-home.acceptance.spec.ts',
  'test/ui-phase4-papers.acceptance.spec.ts',
  'test/ui-phase5-detail.acceptance.spec.ts',
  'test/ui-phase6-graph.acceptance.spec.ts',
  'test/ui-phase7-patrol.acceptance.spec.ts',
  'test/ui-phase8-responsive.acceptance.spec.ts',
  'test/ui-phase141-background.acceptance.spec.ts',
  'test/ui-phase142-layout.acceptance.spec.ts',
  'test/ui-phase143-motion.acceptance.spec.ts',
  'test/ui-phase144-copy.acceptance.spec.ts',
  'test/ui-design-foundation.acceptance.spec.ts',
  'test/ui-antipattern.acceptance.spec.ts',
  'test/demo-path.integration.test.ts',
] as const

const FORBIDDEN_PLACEHOLDERS = ['请输入内容', '请输入…', '请输入问题', 'Lorem ipsum'] as const

const VIEW_FILES = [
  'views/HomeView.vue',
  'views/PapersView.vue',
  'views/PaperDetailView.vue',
  'views/PaperGraphView.vue',
  'views/PatrolView.vue',
  'components/layout/AppLayout.vue',
] as const

function collectSourceFiles(relativeDir: string, extensions: string[]): string[] {
  const absoluteDir = resolve(FRONTEND_SRC, relativeDir)
  const files: string[] = []

  for (const entry of readdirSync(absoluteDir)) {
    const fullPath = join(absoluteDir, entry)
    if (statSync(fullPath).isDirectory()) {
      files.push(...collectSourceFiles(join(relativeDir, entry), extensions))
      continue
    }
    if (extensions.some((ext) => entry.endsWith(ext))) {
      files.push(join(relativeDir, entry).replace(/\\/g, '/'))
    }
  }

  return files
}

function readSrc(relativePathFromSrc: string): string {
  return readFileSync(resolve(FRONTEND_SRC, relativePathFromSrc), 'utf8')
}

function extractStyleBlocks(src: string): string {
  return [...src.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((match) => match[1] ?? '').join('\n')
}

describe('§9 Experience quality × Phase checklist (full audit)', () => {
  describe('Phase acceptance suite registry', () => {
    it.each(PHASE_ACCEPTANCE_FILES)('keeps %s in repo for phase regression', (relativePath) => {
      expect(existsSync(resolve(FRONTEND_SRC, relativePath))).toBe(true)
    })

    it('keeps graph-qa integration for Citation ↔ Graph linkage', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/graph-qa.integration.test.ts'))).toBe(true)
    })
  })

  describe('Phase 0 — design foundation', () => {
    const tokens = loadDesignTokenMap()
    const tokensCss = readSrc('styles/tokens.css')
    const typographyCss = readSrc('styles/typography.css')
    const mainTs = readSrc('main.ts')

    it('§1.4.1: three background layers + primary discipline in tokens.css', () => {
      expect(tokens['--color-bg-page']).toBe('#f8f9fb')
      expect(tokens['--color-bg-surface']).toBe('#ffffff')
      expect(tokens['--color-bg-canvas']).toBe('#f1f5f9')
      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(tokens['--color-primary']).toBe('#0d6e6e')
      expect(tokens['--color-primary-light']).toBe('#e6f3f3')
      expect(tokens['--color-citation-active']).toBe('#e11d48')
      expect(tokensCss).not.toContain('#409eff')
      expect(tokensCss).toContain('§1.4.1 three-layer discipline')
    })

    it('§1.4.2: typography utility classes map to token scale', () => {
      expect(typographyCss).toContain('.text-display')
      expect(typographyCss).toContain('.text-h1')
      expect(typographyCss).toContain('.text-body-lg')
      expect(typographyCss).toContain('.text-mono')
      expect(typographyCss).toContain('var(--text-h1-size)')
    })

    it('§1.4.3: motion CSS variables use ease-out-product (not ease-in-out default)', () => {
      expect(tokens['--duration-instant']).toBe('120ms')
      expect(tokens['--duration-fast']).toBe('150ms')
      expect(tokens['--duration-normal']).toBe('200ms')
      expect(tokens['--duration-slow']).toBe('250ms')
      expect(tokensCss).toContain('--ease-out-product')
      expect(tokensCss).toContain('@media (prefers-reduced-motion: reduce)')
    })

    it('bootstraps tokens + typography + element theme from main.ts', () => {
      expect(mainTs).toContain('@/styles/tokens.css')
      expect(mainTs).toContain('@/styles/typography.css')
      expect(mainTs).toContain('@/styles/element-theme.scss')
    })
  })

  describe('Phase 1 — App Shell', () => {
    const appLayoutSrc = readSrc('components/layout/AppLayout.vue')

    it('§1.4.1: separates page (main) and surface (aside/header) backgrounds', () => {
      expect(appLayoutSrc).toContain('background: var(--color-bg-page)')
      expect(appLayoutSrc).toContain('background: var(--color-bg-surface)')
    })

    it('§1.4.2: 240px aside, 56px header, 44px nav item rhythm', () => {
      expect(appLayoutSrc).toContain('width="240px"')
      expect(appLayoutSrc).toContain('height: 56px')
      expect(appLayoutSrc).toContain('height: 44px')
    })

    it('§1.4.3: nav hover uses 120ms instant transition on explicit properties', () => {
      expect(appLayoutSrc).toContain('var(--transition-instant)')
      expect(appLayoutSrc).not.toMatch(/transition:\s*all/i)
    })

    it('§1.4.4: header title binds route.meta.title with ScholarGraph fallback', () => {
      expect(appLayoutSrc).toContain('route.meta.title')
      expect(appLayoutSrc).toContain("'ScholarGraph'")
    })
  })

  describe('Phase 2 — shared UI components', () => {
    const badgeParadigmSrc = readSrc('components/ui/BadgeParadigm.vue')
    const tagCitationSrc = readSrc('components/ui/TagCitation.vue')
    const emptyStateSrc = readSrc('components/ui/emptyStatePresets.ts')

    it('§1.4.1: BadgeParadigm uses semantic paradigm tokens', () => {
      expect(badgeParadigmSrc).toContain('var(--color-hss-bg)')
      expect(badgeParadigmSrc).toContain('var(--color-stem-bg)')
    })

    it('§1.4.2: TagCitation enforces compact pill sizing', () => {
      expect(tagCitationSrc).toContain('tag-citation')
      expect(tagCitationSrc).toContain('border-radius: var(--radius-md)')
      expect(tagCitationSrc).toContain('padding: var(--spacing-4) var(--spacing-12)')
    })

    it('§1.4.3: TagCitation hover 120ms + active 150ms transitions', () => {
      expect(tagCitationSrc).toContain('var(--transition-instant)')
      expect(tagCitationSrc).toContain('var(--transition-fast)')
    })

    it('§1.4.4: EmptyState presets carry actionable baseline copy', () => {
      expect(EMPTY_STATE_PRESETS['no-papers'].title).toBe('还没有论文')
      expect(EMPTY_STATE_PRESETS['no-papers'].description).toContain('上传 PDF')
      expect(emptyStateSrc).toContain('no-papers')
    })
  })

  describe('Phase 3 — Home', () => {
    const homeViewSrc = readSrc('views/HomeView.vue')

    it('§1.4.1: hero visual uses canvas mock with surface cards', () => {
      expect(homeViewSrc).toContain('HomeGraphMock')
      expect(readSrc('components/home/HomeGraphMock.vue')).toContain('var(--color-bg-canvas)')
    })

    it('§1.4.2: 58/42 hero grid (non-equal thirds)', () => {
      expect(homeViewSrc).toContain('grid-template-columns: 58fr 42fr')
    })

    it('§1.4.3: quick cards hover uses instant transition', () => {
      expect(homeViewSrc).toContain('var(--transition-instant)')
    })

    it('§1.4.4: hero baseline copy constants are wired', () => {
      expect(homeViewSrc).toContain('HOME_BASELINE_COPY')
      expect(readSrc('constants/homeCopy.ts')).toContain('浏览文献库')
      expect(readSrc('constants/homeCopy.ts')).toContain('解构论文逻辑，')
    })
  })

  describe('Phase 4 — Papers', () => {
    const papersViewSrc = readSrc('views/PapersView.vue')
    const uploadSrc = readSrc('components/papers/PaperUpload.vue')

    it('§1.4.1: upload zone layers subtle canvas with primary-light drag-over', () => {
      expect(uploadSrc).toContain('var(--color-bg-subtle)')
      expect(uploadSrc).toContain('var(--color-primary-light)')
      expect(uploadSrc).toContain('border-radius: var(--radius-xl)')
    })

    it('§1.4.2: table uses compact 52px row rhythm', () => {
      expect(papersViewSrc).toContain('height: 52px')
    })

    it('§1.4.3: upload drag-over uses instant border/background transition', () => {
      expect(uploadSrc).toContain('var(--transition-instant)')
      expect(uploadSrc).not.toMatch(/transition:\s*all/i)
    })

    it('§1.4.4: upload + empty baseline copy is centralized', () => {
      expect(uploadSrc).toContain('PAPERS_BASELINE_COPY')
      expect(readSrc('constants/papersCopy.ts')).toContain('拖拽 PDF 到此处')
      expect(papersViewSrc).toContain('EmptyState')
      expect(papersViewSrc).toContain('variant="no-papers"')
    })
  })

  describe('Phase 5 — Detail', () => {
    const detailViewSrc = readSrc('views/PaperDetailView.vue')
    const statusPanelSrc = readSrc('components/papers/PaperStatusPanel.vue')
    const tokens = loadDesignTokenMap()

    it('§1.4.1: answer panel uses subtle embedded surface (#FAFBFC token)', () => {
      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(detailViewSrc).toContain('var(--color-bg-subtle)')
    })

    it('§1.4.2: dual-column layout + metadata → QA → graph sightline', () => {
      expect(detailViewSrc).toContain('grid-template-columns: 45fr 55fr')
      expect(detailViewSrc.indexOf('detail-main')).toBeLessThan(detailViewSrc.indexOf('detail-graph'))
      expect(detailViewSrc.indexOf('PaperMetadataCard')).toBeLessThan(detailViewSrc.indexOf('detail-qa'))
    })

    it('§1.4.3: Citation 150ms, SSE cursor blink, Step pulse with reduced-motion guard', () => {
      expect(readSrc('components/ui/TagCitation.vue')).toContain('var(--transition-fast)')
      expect(detailViewSrc).toContain('detail-qa-cursor-blink')
      expect(detailViewSrc).toContain('prefers-reduced-motion')
      expect(statusPanelSrc).toContain('status-step-pulse')
      expect(statusPanelSrc).toContain('prefers-reduced-motion')
    })

    it('§1.4.4: Step / Alert / QA placeholder baseline copy', () => {
      expect(PIPELINE_STEPS.map((step) => step.label)).toEqual([
        '正在解析 PDF',
        '精炼文档头部',
        '范式分类',
        '抽取图谱',
        '写入存储',
        '建图完成',
      ])
      expect(DETAIL_BASELINE_COPY.notReadyAlert).toContain('尚未 ready')
      expect(DETAIL_BASELINE_COPY.qaPlaceholder).toContain('核心论点')
    })
  })

  describe('Phase 6 — Graph', () => {
    const graphViewSrc = readSrc('views/PaperGraphView.vue')
    const drawerSrc = readSrc('components/graph/GraphNodeDrawer.vue')
    const paperGraphUtilSrc = readSrc('utils/paperGraph.ts')

    it('§1.4.1: canvas full-bleed + legend/drawer surface float layers', () => {
      expect(graphViewSrc).toContain('var(--color-bg-canvas)')
      expect(readSrc('components/graph/GraphLegend.vue')).toContain('var(--color-bg-surface)')
      expect(drawerSrc).toContain('var(--color-bg-surface)')
      expect(readSrc('utils/paperGraph.ts')).toContain('GRAPH_NODE_SURFACE_FILL')
      expect(readSrc('utils/paperGraph.ts')).toContain('shadowBlur')
    })

    it('§1.4.2: graph route is fullBleed with min 720px stage', () => {
      const graphRoute = routes.find((route) => route.name === RouteName.PaperGraph)
      expect(graphRoute?.meta?.fullBleed).toBe(true)
      expect(graphViewSrc).toContain('min-height: 720px')
    })

    it('§1.4.3: node stroke 120ms + drawer 250ms without hover displacement', () => {
      expect(GRAPH_STATE_ANIMATION_MS).toBe(120)
      expect(drawerSrc).toContain('var(--transition-slow)')
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\.05/)
      expect(paperGraphUtilSrc).toContain("fields: ['stroke', 'lineWidth', 'fill']")
    })

    it('§1.4.4: 409 graph-not-ready error title + CTA baseline', () => {
      expect(GRAPH_BASELINE_COPY.graphNotReadyTitle).toBe('图谱未就绪')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY.graphNotReadyCta')
      expect(graphViewSrc).toContain('graph-view__error-cta')
    })
  })

  describe('Phase 7 — Patrol', () => {
    const patrolViewSrc = readSrc('views/PatrolView.vue')
    const insightCardSrc = readSrc('components/ui/InsightCard.vue')

    it('§1.4.1: insight cards use surface token with semantic left border', () => {
      expect(insightCardSrc).toContain('background: var(--color-bg-surface)')
      expect(patrolViewSrc).toContain('InsightCard')
    })

    it('§1.4.2: config form + report sections are separated', () => {
      expect(patrolViewSrc).toContain('patrol-view__config')
      expect(patrolViewSrc).toContain('patrol-view__report')
    })

    it('§1.4.3: segmented control switches modes with primary active state', () => {
      expect(patrolViewSrc).toContain('patrol-mode-segment')
      expect(patrolViewSrc).toContain('var(--transition-instant)')
    })

    it('§1.4.4: patrol baseline + error table copy', () => {
      expect(PATROL_BASELINE_COPY.subtitle).toContain('ready 论文')
      expect(PATROL_BASELINE_COPY.insufficientDataCta).toBe('换用论文')
      expect(patrolViewSrc).toContain('patrol-view__error-cta')
    })
  })

  describe('Phase 8 — responsive & final audit', () => {
    const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
    const detailViewSrc = readSrc('views/PaperDetailView.vue')

    it('§1.4.1: style blocks in views/components avoid raw background hex', () => {
      const vueFiles = [...collectSourceFiles('views', ['.vue']), ...collectSourceFiles('components', ['.vue'])]
      for (const file of vueFiles) {
        const styleSrc = extractStyleBlocks(readSrc(file))
        expect(styleSrc.match(/background(?:-color)?:\s*#[0-9a-f]{3,8}/gi) ?? [], file).toEqual([])
      }
    })

    it('§1.4.2: responsive breakpoints for Detail and mobile shell', () => {
      expect(detailViewSrc).toContain('@media (min-width: 1024px) and (max-width: 1279px)')
      expect(appLayoutSrc).toContain('header-menu-toggle')
      expect(appLayoutSrc).toContain('@media (max-width: 767px)')
    })

    it('§1.4.3: route-fade + reduced-motion audit hooks exist', () => {
      expect(appLayoutSrc).toContain('name="route-fade"')
      expect(appLayoutSrc).toContain('prefers-reduced-motion')
      expect(readSrc('styles/tokens.css')).toContain('--duration-blink: 0ms')
    })

    it('§1.4.4: forbidden marketing words scan is covered by phase 8 + §1.3 antipattern acceptance', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-phase8-responsive.acceptance.spec.ts'))).toBe(true)
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-antipattern.acceptance.spec.ts'))).toBe(true)
    })
  })

  describe('§9 背景 §1.4.1 — Phase 对照表验收', () => {
    const tokens = loadDesignTokenMap()
    const phase141Src = readSrc('test/ui-phase141-background.acceptance.spec.ts')

    it('keeps ui-phase141-background acceptance as §1.4.1 automation gate', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-phase141-background.acceptance.spec.ts'))).toBe(true)
      expect(phase141Src).toContain('§1.4.1 Background & color discipline')
      expect(phase141Src).toContain('正文 --color-text-primary 对 surface/page 对比度')
      expect(phase141Src).toContain('图谱节点 surface fill + type stroke')
    })

    it('Phase 0：三层 Token + 主色纪律', () => {
      expect(tokens['--color-bg-page']).toBe('#f8f9fb')
      expect(tokens['--color-bg-surface']).toBe('#ffffff')
      expect(tokens['--color-bg-canvas']).toBe('#f1f5f9')
      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(readSrc('styles/tokens.css')).toContain('--color-primary: #0d6e6e')
      expect(readSrc('assets/main.css')).toContain('var(--color-bg-page)')
    })

    it('Phase 1：page/surface 分层', () => {
      const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
      expect(appLayoutSrc).toContain('background: var(--color-bg-page)')
      expect(appLayoutSrc).toContain('background: var(--color-bg-surface)')
    })

    it('Phase 2：Badge 语义色', () => {
      const badgeParadigmSrc = readSrc('components/ui/BadgeParadigm.vue')
      const badgeStatusSrc = readSrc('components/ui/BadgeStatus.vue')
      expect(badgeParadigmSrc).toContain('var(--color-hss-bg)')
      expect(badgeStatusSrc).toContain('var(--color-success)')
      expect(badgeParadigmSrc).not.toMatch(/#[0-9a-f]{6}/i)
    })

    it('Phase 3：canvas mock 区', () => {
      const homeGraphMockSrc = readSrc('components/home/HomeGraphMock.vue')
      expect(homeGraphMockSrc).toContain('var(--color-bg-canvas)')
      expect(homeGraphMockSrc).toContain('var(--color-bg-surface)')
      expect(readSrc('views/HomeView.vue')).toContain('box-shadow: var(--shadow-sm)')
    })

    it('Phase 4：上传区/表头分层', () => {
      const papersViewSrc = readSrc('views/PapersView.vue')
      const uploadSrc = readSrc('components/papers/PaperUpload.vue')
      expect(papersViewSrc).toContain('var(--color-bg-page)')
      expect(papersViewSrc).toContain('var(--color-bg-subtle)')
      expect(uploadSrc).toContain('var(--color-bg-subtle)')
    })

    it('Phase 5：答案区内嵌灰底', () => {
      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(readSrc('views/PaperDetailView.vue')).toContain('var(--color-bg-subtle)')
    })

    it('Phase 6：canvas + 浮层', () => {
      expect(readSrc('views/PaperGraphView.vue')).toContain('var(--color-bg-canvas)')
      expect(readSrc('components/graph/GraphLegend.vue')).toContain('var(--color-bg-surface)')
      expect(getGraphNodeFillColor('Thesis', 'HSS')).toBe(GRAPH_NODE_SURFACE_FILL)
    })

    it('Phase 7：Insight 卡 surface', () => {
      expect(readSrc('components/ui/InsightCard.vue')).toContain('background: var(--color-bg-surface)')
      expect(readSrc('views/PatrolView.vue')).toContain('var(--color-bg-subtle)')
    })

    it('Phase 8：全站 hex 扫雷 + 对比度门禁', () => {
      expect(phase141Src).toContain('views avoid flat root hex backgrounds')
      expect(
        contrastRatio(tokens['--color-text-primary'] ?? '#111827', tokens['--color-bg-surface'] ?? '#ffffff'),
      ).toBeGreaterThanOrEqual(WCAG_AA_TEXT_CONTRAST)
      const canvasBg = tokens['--color-bg-canvas'] ?? '#f1f5f9'
      for (const strokeColor of listGraphNodeTypeStrokeColors('HSS')) {
        expect(contrastRatio(strokeColor, canvasBg)).toBeGreaterThanOrEqual(WCAG_AA_UI_CONTRAST)
      }
    })

    it('§9 总验收 — 三层背景 discipline：无整页单色、无主色大面积铺底', () => {
      for (const viewPath of VIEW_FILES) {
        const src = readSrc(viewPath)
        expect(
          src.includes('var(--color-bg-page)') ||
            src.includes('var(--color-bg-surface)') ||
            src.includes('var(--color-bg-canvas)') ||
            src.includes('var(--color-bg-subtle)'),
          viewPath,
        ).toBe(true)
      }
      expect(phase141Src).toContain('主色不作视口级容器大底铺色')
    })
  })

  describe('§9 布局 §1.4.2 — Phase 对照表验收', () => {
    const tokens = loadDesignTokenMap()
    const phase142Src = readSrc('test/ui-phase142-layout.acceptance.spec.ts')

    it('keeps ui-phase142-layout acceptance as §1.4.2 automation gate', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-phase142-layout.acceptance.spec.ts'))).toBe(true)
      expect(phase142Src).toContain('§1.4.2 Layout & typography discipline')
      expect(phase142Src).toContain('DESIGN_VARIANCE')
      expect(phase142Src).toContain('Detail left column module order')
    })

    it('Phase 0：typography 工具类 + spacing/radius tokens', () => {
      expect(readSrc('styles/typography.css')).toContain('.text-h1')
      expect(tokens['--spacing-48']).toBe('48px')
      expect(tokens['--radius-xl']).toBe('12px')
      expect(tokens['--content-max-width']).toBe('1280px')
    })

    it('Phase 1：240/56/44 网格', () => {
      const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
      expect(appLayoutSrc).toContain('width="240px"')
      expect(appLayoutSrc).toContain('height: 56px')
      expect(appLayoutSrc).toContain('height: 44px')
    })

    it('Phase 2：组件尺寸统一（TagCitation compact pill）', () => {
      const tagSrc = readSrc('components/ui/TagCitation.vue')
      expect(tagSrc).toContain('border-radius: var(--radius-md)')
      expect(tagSrc).toContain('padding: var(--spacing-4) var(--spacing-12)')
    })

    it('Phase 3：58/42 非对称 + Home 48/64 间距', () => {
      const homeSrc = readSrc('views/HomeView.vue')
      expect(homeSrc).toContain('grid-template-columns: 58fr 42fr')
      expect(homeSrc).toContain('page-content')
      expect(homeSrc).toContain('margin-top: var(--spacing-64)')
    })

    it('Phase 4：高密度表格 52px 行高', () => {
      expect(readSrc('views/PapersView.vue')).toContain('height: 52px')
    })

    it('Phase 5：双栏 45/55 + Detail 视线流', () => {
      const detailSrc = readSrc('views/PaperDetailView.vue')
      expect(detailSrc).toContain('grid-template-columns: 45fr 55fr')
      expect(detailSrc).toContain('gap: var(--spacing-24)')
      expect(countHeadingLevel(detailSrc, 2)).toBeLessThanOrEqual(3)
    })

    it('Phase 6：full-bleed 图谱 stage min 720px', () => {
      expect(readSrc('views/PaperGraphView.vue')).toContain('min-height: 720px')
    })

    it('Phase 7：Patrol 表单 + 报告区分区', () => {
      expect(readSrc('views/PatrolView.vue')).toContain('var(--content-max-width)')
      expect(readSrc('views/PatrolView.vue')).toContain('patrol-view__config')
    })

    it('Phase 8：断点折叠（Detail 1024/1280 + mobile shell）', () => {
      expect(readSrc('views/PaperDetailView.vue')).toContain('@media (min-width: 1024px)')
      expect(readSrc('components/layout/AppLayout.vue')).toContain('@media (max-width: 767px)')
    })

    it('§9 总验收 — 主视图 H2 ≤3、content-max-width 1280', () => {
      for (const viewPath of [
        'views/HomeView.vue',
        'views/PapersView.vue',
        'views/PaperDetailView.vue',
        'views/PatrolView.vue',
      ]) {
        expect(countHeadingLevel(readSrc(viewPath), 2)).toBeLessThanOrEqual(3)
      }
      expect(readSrc('assets/main.css')).toContain('var(--content-max-width)')
    })

    it('§9 布局验收 checklist — phase142 四项门禁已注册', () => {
      expect(phase142Src).toContain('§1.4.2 布局验收 — checklist')
      expect(phase142Src).toContain('Home：58/42 hero + 底部 60/40 quick links')
      expect(phase142Src).toContain('Detail：≥1024px 双栏 45/55')
      expect(phase142Src).toContain('表格 / Stepper / 表单对齐网格')
    })
  })

  describe('§9 动效 §1.4.3 — Phase 对照表验收', () => {
    const tokens = loadDesignTokenMap()
    const phase143Src = readSrc('test/ui-phase143-motion.acceptance.spec.ts')

    it('keeps ui-phase143-motion acceptance as §1.4.3 automation gate', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-phase143-motion.acceptance.spec.ts'))).toBe(true)
      expect(phase143Src).toContain('§1.4.3 Motion & interaction discipline')
      expect(phase143Src).toContain('§1.4.3 动效验收 — checklist')
    })

    it('Phase 0：动效 CSS 变量', () => {
      expect(tokens['--duration-instant']).toBe('120ms')
      expect(tokens['--ease-out-product']).toContain('cubic-bezier')
      expect(readSrc('styles/tokens.css')).toContain('--transition-instant')
    })

    it('Phase 1：Nav hover 120ms', () => {
      expect(readSrc('components/layout/AppLayout.vue')).toContain('var(--transition-instant)')
    })

    it('Phase 2：Tag hover 120ms', () => {
      expect(readSrc('components/ui/TagCitation.vue')).toContain('var(--transition-instant)')
    })

    it('Phase 3：卡片 hover 120ms', () => {
      expect(readSrc('views/HomeView.vue')).toContain('var(--transition-instant)')
    })

    it('Phase 4：Upload drag-over 120ms', () => {
      expect(readSrc('components/papers/PaperUpload.vue')).toContain('var(--transition-instant)')
    })

    it('Phase 5：Citation 150ms、SSE 光标、Step 脉冲', () => {
      expect(readSrc('components/ui/TagCitation.vue')).toContain('var(--transition-fast)')
      expect(readSrc('views/PaperDetailView.vue')).toContain('detail-qa-cursor-blink')
      expect(readSrc('components/papers/PaperStatusPanel.vue')).toContain('status-step-pulse')
    })

    it('Phase 6：Graph 节点 120ms + Drawer 250ms', () => {
      expect(readSrc('utils/paperGraph.ts')).toContain('GRAPH_STATE_ANIMATION_MS')
      expect(readSrc('components/graph/GraphNodeDrawer.vue')).toContain('var(--transition-slow)')
    })

    it('Phase 7：Segmented 切换 instant 颜色反馈', () => {
      expect(readSrc('views/PatrolView.vue')).toContain('var(--transition-instant)')
    })

    it('Phase 8：route-fade + reduced-motion 审计', () => {
      expect(readSrc('components/layout/AppLayout.vue')).toContain('route-fade')
      expect(readSrc('test/ui-phase8-responsive.acceptance.spec.ts')).toContain('prefers-reduced-motion audit')
    })

    it('§9 总验收 — focus-visible ring + 无 transition:all', () => {
      expect(readSrc('assets/main.css')).toContain(':focus-visible')
      expect(phase143Src).toContain('无任何 transition: all')
    })

    it('§9 动效验收 checklist — phase143 + graph-qa + demo-path 三门禁', () => {
      expect(phase143Src).toContain('Citation 点击后 Tag 与节点同一帧内开始变化')
      expect(phase143Src).toContain('演示时动效不遮挡 SSE 阅读与图谱节点 label')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.3 motion acceptance checklist')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.3 动效验收 checklist')
    })
  })

  describe('§9 文案 §1.4.4 — Phase 对照表验收', () => {
    const phase144Src = readSrc('test/ui-phase144-copy.acceptance.spec.ts')

    it('keeps ui-phase144-copy acceptance as §1.4.4 automation gate', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-phase144-copy.acceptance.spec.ts'))).toBe(true)
      expect(phase144Src).toContain('§1.4.4 排版验收 — checklist')
    })

    it('Phase 0：typography 工具类（Display / H1–H3 / Body / Body-lg / Mono）', () => {
      const typographyCss = readSrc('styles/typography.css')
      expect(typographyCss).toContain('.text-body-lg')
      expect(typographyCss).toContain('.text-mono')
      expect(typographyCss).toContain('Body-lg QA')
    })

    it('Phase 1：route title 文案（App Shell）', () => {
      expect(readSrc('constants/shellCopy.ts')).toContain('SHELL_BASELINE_COPY')
      expect(readSrc('components/layout/AppLayout.vue')).toContain('route.meta.title')
    })

    it('Phase 2：Empty 默认文案', () => {
      expect(readSrc('components/ui/emptyStatePresets.ts')).toContain('PAPERS_BASELINE_COPY')
      expect(EMPTY_STATE_PRESETS['no-papers'].title).toBe('还没有论文')
    })

    it('Phase 3：Home 基准表全文 + 副标题 secondary', () => {
      expect(readSrc('constants/homeCopy.ts')).toContain('HOME_BASELINE_COPY')
      expect(readSrc('views/HomeView.vue')).toContain('HOME_BASELINE_COPY')
      expect(readSrc('views/HomeView.vue')).toMatch(/\.home-subtitle[\s\S]*color: var\(--color-text-secondary\)/)
    })

    it('Phase 4：Upload / Empty 基准 + upload tip secondary', () => {
      expect(readSrc('constants/papersCopy.ts')).toContain('PAPERS_BASELINE_COPY')
      expect(readSrc('components/papers/PaperUpload.vue')).toContain('PAPERS_BASELINE_COPY')
    })

    it('Phase 5：答案区内嵌灰底 + Step/Alert/placeholder', () => {
      expect(readSrc('constants/detailCopy.ts')).toContain('DETAIL_BASELINE_COPY')
      expect(phase144Src).toContain('问答答案区：Body-lg + pre-wrap + 内嵌灰底，长答案可读')
      expect(DETAIL_BASELINE_COPY.qaPlaceholder).toContain('核心论点')
    })

    it('Phase 6：409 错误文案 + CTA', () => {
      expect(GRAPH_BASELINE_COPY.graphNotReadyTitle).toBe('图谱未就绪')
      expect(readSrc('views/PaperGraphView.vue')).toContain('graph-view__error-cta')
    })

    it('Phase 7：Patrol 基准 + 错误表 + 副标题 secondary', () => {
      expect(PATROL_BASELINE_COPY.subtitle).toContain('ready 论文')
      expect(readSrc('views/PatrolView.vue')).toMatch(
        /\.patrol-view__subtitle[\s\S]*color: var\(--color-text-secondary\)/,
      )
    })

    it('Phase 8：禁止词扫雷（ui-antipattern + phase144）', () => {
      expect(readSrc('test/ui-antipattern.acceptance.spec.ts')).toContain('无产品黑话')
      expect(phase144Src).toContain('禁止词表')
    })

    it('§9 排版验收 checklist — phase144 + graph-qa + demo-path 三门禁', () => {
      expect(phase144Src).toContain('Mono 仅 ID / code，正文不整段 Mono')
      expect(phase144Src).toContain('中文与英文/ID 混排：label 正文 + (node_id) Mono 括号')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.4 typography acceptance checklist')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.4 排版验收 checklist')
      expect(readSrc('views/PaperDetailView.spec.ts')).toContain('§1.4.4 typography checklist')
    })
  })

  describe('§9 总验收 — cross-cutting gates', () => {
    const styleSources = [
      ...collectSourceFiles('views', ['.vue']),
      ...collectSourceFiles('components', ['.vue']),
      ...collectSourceFiles('styles', ['.css', '.scss']),
    ]

    it('background discipline: primary views use layered bg tokens (not flat root hex)', () => {
      for (const viewPath of VIEW_FILES) {
        const src = readSrc(viewPath)
        const hasLayeredBg =
          src.includes('var(--color-bg-page)') ||
          src.includes('var(--color-bg-surface)') ||
          src.includes('var(--color-bg-canvas)') ||
          src.includes('var(--color-bg-subtle)')
        expect(hasLayeredBg, `${viewPath} should reference bg layer tokens`).toBe(true)
      }
    })

    it('background discipline: text primary meets WCAG AA on page/surface (§1.4.1)', () => {
      const tokens = loadDesignTokenMap()
      const textPrimary = tokens['--color-text-primary'] ?? '#111827'
      expect(contrastRatio(textPrimary, tokens['--color-bg-surface'] ?? '#ffffff')).toBeGreaterThanOrEqual(
        WCAG_AA_TEXT_CONTRAST,
      )
      expect(contrastRatio(textPrimary, tokens['--color-bg-page'] ?? '#f8f9fb')).toBeGreaterThanOrEqual(
        WCAG_AA_TEXT_CONTRAST,
      )
    })

    it('layout discipline: §1.4.2 checklist — Home asymmetric, Detail sightline, no magic spacing', () => {
      const phase142Src = readSrc('test/ui-phase142-layout.acceptance.spec.ts')
      expect(phase142Src).toContain('§1.4.2 布局验收 — checklist')
      expect(readSrc('views/HomeView.vue')).toContain('grid-template-columns: 58fr 42fr')
      expect(readSrc('views/PaperDetailView.vue')).toContain('grid-template-columns: 45fr 55fr')
      expect(readSrc('components/layout/AppLayout.vue')).toContain('padding: var(--spacing-24) var(--spacing-32)')
    })

    it('motion discipline: §1.4.3 checklist — Citation sync, no transition:all, demo readability', () => {
      const phase143Src = readSrc('test/ui-phase143-motion.acceptance.spec.ts')
      expect(phase143Src).toContain('Citation 点击后 Tag 与节点同一帧内开始变化')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.3 motion acceptance checklist')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.3 动效验收 checklist')
      expect(loadDesignTokenMap()['--duration-fast']).toBe('150ms')
    })

    it('motion discipline: src/ has no transition:all or ease-in-out keyword defaults', () => {
      for (const relativePath of styleSources) {
        const src = extractStyleBlocks(readSrc(relativePath))
        expect(src, relativePath).not.toMatch(/transition:\s*all/i)
        expect(src, relativePath).not.toMatch(/ease-in-out/i)
      }
    })

    it('motion discipline: graph node hover does not translate nodes', () => {
      const paperGraphUtilSrc = readSrc('utils/paperGraph.ts')
      expect(paperGraphUtilSrc).not.toMatch(/translate/i)
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\./)
    })

    it('copy discipline: no forbidden empty placeholders in views/constants', () => {
      const copySources = [...collectSourceFiles('views', ['.vue']), ...collectSourceFiles('constants', ['.ts'])]
      for (const relativePath of copySources) {
        const src = readSrc(relativePath)
        for (const phrase of FORBIDDEN_PLACEHOLDERS) {
          expect(src, `${relativePath} must not contain "${phrase}"`).not.toContain(phrase)
        }
      }
    })

    it('copy discipline: Empty / Error surfaces expose next-step CTAs', () => {
      expect(readSrc('views/PapersView.vue')).toContain('papers-empty')
      expect(readSrc('views/PaperGraphView.vue')).toContain('graph-view__error-cta')
      expect(readSrc('views/PatrolView.vue')).toContain('patrol-view__error-cta')
      expect(readSrc('components/papers/PaperUpload.vue')).toMatch(/uploadRetry|PAPERS_BASELINE_COPY/)
    })

    it('typography discipline: §1.4.4 checklist via phase144 + graph-qa + demo-path', () => {
      const phase144Src = readSrc('test/ui-phase144-copy.acceptance.spec.ts')
      expect(phase144Src).toContain('§1.4.4 排版验收 — checklist')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.4 typography acceptance checklist')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.4 排版验收 checklist')
    })

    it('demo path §6: router resolves Home → Papers → Detail → Graph → Patrol chain', () => {
      const routeNames = routes.map((route) => route.name)
      expect(routeNames).toEqual(
        expect.arrayContaining([
          RouteName.Home,
          RouteName.Papers,
          RouteName.PaperDetail,
          RouteName.PaperGraph,
          RouteName.Patrol,
        ]),
      )

      const homeSrc = readSrc('views/HomeView.vue')
      expect(homeSrc).toContain('to="/papers"')
      expect(homeSrc).toContain('to="/patrol"')
      expect(homeSrc).toContain('to="/papers/hss-001"')
    })

    it('Citation ↔ Graph 150ms: shared active token + TagCitation fast transition + highlight map', () => {
      const tokens = loadDesignTokenMap()
      const tagSrc = readSrc('components/ui/TagCitation.vue')
      const graphQaSrc = readSrc('test/graph-qa.integration.test.ts')

      expect(tokens['--duration-fast']).toBe('150ms')
      expect(tokens['--color-citation-active']).toBe('#e11d48')
      expect(tagSrc).toContain('var(--color-citation-active)')
      expect(tagSrc).toContain('var(--transition-fast)')
      expect(graphQaSrc).toContain('buildHighlightStateMap')
      expect(readSrc('utils/paperGraph.ts')).toContain('active')
    })

    it('check:ci gate is documented in frontend package.json', () => {
      const packageJson = JSON.parse(readFileSync(resolve(FRONTEND_ROOT, 'package.json'), 'utf8')) as {
        scripts: Record<string, string>
      }
      expect(packageJson.scripts['check:ci']).toContain('npm run check')
      expect(packageJson.scripts['check:ci']).toContain('npm run test')
      expect(packageJson.scripts['check:ci']).toContain('npm run build')
    })

    it('§1.3 anti-pattern checklist: dedicated acceptance covers visual, motion, and copy gates', () => {
      const antipatternSrc = readSrc('test/ui-antipattern.acceptance.spec.ts')
      expect(antipatternSrc).toContain('§1.3 Anti-pattern checklist')
      expect(antipatternSrc).toContain('无 Inter 字体栈')
      expect(antipatternSrc).toContain('无裸 transition: all')
      expect(antipatternSrc).toContain('无产品黑话')
      expect(antipatternSrc).toContain('图谱节点 hover 禁止位移')
    })

    it('§1.4.1 background gate: ui-phase141 covers contrast + card layering', () => {
      const phase141Src = readSrc('test/ui-phase141-background.acceptance.spec.ts')
      expect(phase141Src).toContain('semantic status tokens stay within badge/alert allowlist')
      expect(phase141Src).toContain('CARD_SURFACE_FILES')
    })

    it('§1.4.2 layout gate: ui-phase142 covers spacing scale + Detail sightline', () => {
      const phase142Src = readSrc('test/ui-phase142-layout.acceptance.spec.ts')
      expect(phase142Src).toContain('VISUAL_DENSITY')
      expect(phase142Src).toContain('each primary view keeps ≤3 H2 section titles per screen')
      expect(phase142Src).toContain('WORKBENCH_LAYOUT_FILES')
    })

    it('§1.4.3 motion gate: ui-phase143 + graph-qa + demo-path cover motion checklist', () => {
      const phase143Src = readSrc('test/ui-phase143-motion.acceptance.spec.ts')
      expect(phase143Src).toContain('REDUCED_MOTION_ANIMATION_SOURCES')
      expect(phase143Src).toContain('registers graph-qa and demo-path integration gates')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('preserves readable node labels')
    })

    it('§1.4.4 copy gate: ui-phase144 covers baseline table + typography + forbidden words', () => {
      const phase144Src = readSrc('test/ui-phase144-copy.acceptance.spec.ts')
      expect(phase144Src).toContain('§1.4.4 Copy & typography discipline')
      expect(phase144Src).toContain('各页文案基准表')
      expect(phase144Src).toContain('§1.4.4 排版验收 — checklist')
      expect(phase144Src).toContain('禁止词表')
      expect(readSrc('constants/homeCopy.ts')).toContain('HOME_BASELINE_COPY')
      expect(readSrc('constants/papersCopy.ts')).toContain('PAPERS_BASELINE_COPY')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.4 typography acceptance checklist')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.4 排版验收 checklist')
    })

    it('§1.2 / §1.5 foundation gate: ui-design-foundation covers decisions + parameter table', () => {
      const foundationSrc = readSrc('test/ui-design-foundation.acceptance.spec.ts')
      expect(foundationSrc).toContain('§1.5 设计参数速查')
      expect(foundationSrc).toContain('§1.2 核心设计决策')
      expect(foundationSrc).toContain('1440×900')
      expect(foundationSrc).toContain('答辩必测联动 Tag click')
      expect(readSrc('test/helpers/designFoundationDiscipline.ts')).toContain('DESIGN_CONTENT_MAX_WIDTH')
    })
  })
})
