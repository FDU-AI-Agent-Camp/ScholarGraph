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
import { loadDesignTokenMap } from '@/test/helpers/designTokens'

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
      expect(tokens['--color-primary']).toBe('#0d6e6e')
      expect(tokensCss).not.toContain('#409eff')
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
      expect(homeViewSrc).toContain('上传论文')
      expect(homeViewSrc).toContain('浏览文献库')
      expect(homeViewSrc).toContain('解构论文逻辑，')
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
      expect(uploadSrc).toContain('拖拽 PDF 到此处')
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

    it('§1.4.4: forbidden marketing words scan is covered by phase 8 acceptance', () => {
      expect(existsSync(resolve(FRONTEND_SRC, 'test/ui-phase8-responsive.acceptance.spec.ts'))).toBe(true)
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
          src.includes('var(--color-bg-canvas)')
        expect(hasLayeredBg, `${viewPath} should reference bg layer tokens`).toBe(true)
      }
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
      expect(readSrc('components/papers/PaperUpload.vue')).toMatch(/重试|上传/)
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
  })
})
