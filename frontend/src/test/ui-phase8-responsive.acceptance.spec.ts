/**
 * Phase 8 acceptance (8.1–8.8) — design-spec §13–§14 + ui-design-progress §1.4 + §6 demo path.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { MOBILE_NAV_MAX_WIDTH_PX } from '@/constants/shellCopy'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const appLayoutSrc = readFrontendSource('components/layout/AppLayout.vue')
const detailViewSrc = readFrontendSource('views/PaperDetailView.vue')
const graphViewSrc = readFrontendSource('views/PaperGraphView.vue')
const homeViewSrc = readFrontendSource('views/HomeView.vue')
const routerSrc = readFrontendSource('router/index.ts')
const tokensCss = readFileSync(resolve(FRONTEND_SRC, 'styles/tokens.css'), 'utf8')

/** ui-design-progress §1.4.4 forbidden marketing / placeholder words. */
const FORBIDDEN_COPY_WORDS = [
  '卓越',
  '赋能',
  '一站式',
  '一体化解决方案',
  '极致',
  '无缝',
  '助力',
  '打造',
  'Lorem',
  'TODO 文案',
] as const

/** Files allowed to declare literal hex outside tokens (design-spec exceptions). */
const HEX_ALLOWLIST: Record<string, RegExp[]> = {
  'components/ui/InsightCard.vue': [/border-left:\s*4px\s+solid\s+#ca8a04/i],
  'views/PatrolView.vue': [/color:\s*#ffffff/i],
}

function collectVueFiles(relativeDir: string): string[] {
  const absoluteDir = resolve(FRONTEND_SRC, relativeDir)
  const files: string[] = []

  for (const entry of readdirSync(absoluteDir)) {
    const fullPath = join(absoluteDir, entry)
    if (statSync(fullPath).isDirectory()) {
      files.push(...collectVueFiles(join(relativeDir, entry)))
    } else if (entry.endsWith('.vue')) {
      files.push(join(relativeDir, entry).replace(/\\/g, '/'))
    }
  }

  return files
}

function readVueSource(relativePathFromSrc: string): string {
  return readFileSync(resolve(FRONTEND_SRC, relativePathFromSrc), 'utf8')
}

function extractStyleBlocks(src: string): string {
  return [...src.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((match) => match[1] ?? '').join('\n')
}
describe('Phase 8 responsive & final acceptance (8.1–8.8)', () => {
  describe('8.1 route fade + translateY(8px) 200ms', () => {
    it('wraps router-view in route-fade transition using normal duration token', () => {
      const tokens = loadDesignTokenMap()

      expect(appLayoutSrc).toContain('<transition name="route-fade" mode="out-in">')
      expect(appLayoutSrc).toContain('translateY(8px)')
      expect(appLayoutSrc).toContain('var(--duration-normal)')
      expect(tokens['--duration-normal']).toBe('200ms')
    })
  })

  describe('8.2 Detail breakpoints §1.4.2 / design-spec §14', () => {
    it('uses 50/50 grid at 1024–1279 and 45/55 from 1280', () => {
      expect(detailViewSrc).toContain('@media (min-width: 1024px) and (max-width: 1279px)')
      expect(detailViewSrc).toContain('grid-template-columns: 1fr 1fr')
      expect(detailViewSrc).toContain('@media (min-width: 1280px)')
      expect(detailViewSrc).toContain('grid-template-columns: 45fr 55fr')
    })

    it('defaults to single column for metadata → QA → graph DOM order below 1024', () => {
      expect(detailViewSrc).toContain('grid-template-columns: 1fr')
      expect(detailViewSrc.indexOf('detail-main')).toBeLessThan(detailViewSrc.indexOf('detail-graph'))
      expect(detailViewSrc.indexOf('PaperMetadataCard')).toBeLessThan(detailViewSrc.indexOf('detail-qa'))
      expect(detailViewSrc.indexOf('detail-qa')).toBeLessThan(detailViewSrc.indexOf('detail-graph'))
    })
  })

  describe('8.3 mobile hamburger + Graph desktop banner', () => {
    it('exposes hamburger toggle under 768px and closes nav on route change', () => {
      expect(MOBILE_NAV_MAX_WIDTH_PX).toBe(767)
      expect(appLayoutSrc).toContain('header-menu-toggle')
      expect(appLayoutSrc).toContain('SHELL_BASELINE_COPY.mobileNavToggleLabel')
      expect(appLayoutSrc).toContain('@media (max-width: 767px)')
      expect(appLayoutSrc).toContain('aside--open')
      expect(appLayoutSrc).toContain('watch(')
      expect(appLayoutSrc).toContain('route.path')
    })

    it('shows Graph mobile desktop recommendation banner copy', () => {
      expect(graphViewSrc).toContain('graph-view__mobile-banner')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY.mobileDesktopBanner')
      expect(graphViewSrc).toContain('@media (max-width: 767px)')
      expect(GRAPH_BASELINE_COPY.mobileDesktopBanner).toContain('建议使用桌面浏览器')
    })
  })

  describe('8.4 prefers-reduced-motion audit §1.4.3', () => {
    const animationSources = [
      'components/layout/AppLayout.vue',
      'components/ui/BadgeStatus.vue',
      'components/papers/PaperStatusPanel.vue',
      'components/graph/GraphNodeDrawer.vue',
      'views/PaperDetailView.vue',
    ]

    it('zeros blink duration in tokens reduced-motion block', () => {
      const reduceBlock = tokensCss.match(/@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\}/)?.[1] ?? ''
      expect(reduceBlock).toContain('--duration-blink: 0ms')
    })

    it('disables route slide and mobile drawer slide under reduced motion', () => {
      expect(appLayoutSrc).toContain('@media (prefers-reduced-motion: reduce)')
      expect(appLayoutSrc).toContain('.route-fade-enter-active')
      expect(appLayoutSrc).toContain('transition: none')
    })

    it.each(animationSources)('%s handles prefers-reduced-motion for local animations', (relativePath) => {
      const src = readVueSource(relativePath)
      if (src.includes('@keyframes') || src.includes('name="route-fade"') || src.includes('transform: translateX')) {
        expect(src).toContain('@media (prefers-reduced-motion: reduce)')
      }
    })
  })

  describe('8.5 forbidden copy sweep §1.4.4', () => {
    const vueSources = [...collectVueFiles('views'), ...collectVueFiles('components')]

    it.each(vueSources)('%s contains no forbidden marketing words', (relativePath) => {
      const src = readVueSource(relativePath)
      for (const word of FORBIDDEN_COPY_WORDS) {
        expect(src, `${relativePath} must not contain "${word}"`).not.toContain(word)
      }
    })
  })

  describe('8.6 background layer hex sweep (no private large color blocks)', () => {
    const vueSources = [...collectVueFiles('views'), ...collectVueFiles('components')]

    it.each(vueSources)('%s does not set background with raw hex literals', (relativePath) => {
      const styleSrc = extractStyleBlocks(readVueSource(relativePath))
      const backgroundHexMatches = styleSrc.match(/background(?:-color)?:\s*#[0-9a-f]{3,8}/gi) ?? []
      expect(backgroundHexMatches).toEqual([])
    })

    it.each(vueSources)('%s only uses allowlisted inline hex in styles when present', (relativePath) => {
      const styleSrc = extractStyleBlocks(readVueSource(relativePath))
      const hexMatches = styleSrc.match(/#[0-9a-f]{3,8}/gi) ?? []
      if (hexMatches.length === 0) {
        return
      }

      const allowPatterns = HEX_ALLOWLIST[relativePath] ?? []
      const stripped = styleSrc.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
      for (const hex of hexMatches) {
        const allowed = allowPatterns.some((pattern) => pattern.test(stripped) && stripped.includes(hex))
        expect(allowed, `${relativePath} has unexpected hex ${hex} in styles`).toBe(true)
      }
    })
  })

  describe('8.8 demo defense path §6 + §9 total acceptance', () => {
    it('wires Home → Papers → Detail → Graph → Patrol navigation chain', () => {
      expect(homeViewSrc).toContain('to="/papers"')
      expect(homeViewSrc).toContain('to="/patrol"')
      expect(homeViewSrc).toContain('to="/papers/hss-001"')
      expect(routerSrc).toContain('name: RouteName.Home')
      expect(routerSrc).toContain('name: RouteName.Papers')
      expect(routerSrc).toContain('name: RouteName.PaperDetail')
      expect(routerSrc).toContain('name: RouteName.PaperGraph')
      expect(routerSrc).toContain('name: RouteName.Patrol')
    })

    it('keeps baseline copy anchors for demo storytelling', () => {
      expect(DETAIL_BASELINE_COPY.qaPlaceholder).toContain('核心论点')
      expect(GRAPH_BASELINE_COPY.pageTitle).toBe('逻辑图谱')
      expect(PATROL_BASELINE_COPY.runButton).toBe('运行巡检')
      expect(PATROL_BASELINE_COPY.nodeRefGraphLink).toBe('查看图谱')
    })

    it('supports Graph deep-link query for Patrol node_refs handoff', () => {
      expect(graphViewSrc).toContain('route.query.node')
      const patrolBundle = [
        readFrontendSource('views/PatrolView.vue'),
        readFrontendSource('utils/patrolViewHelpers.ts'),
      ].join('\n')
      expect(patrolBundle).toContain('query: { node: ref.node_id }')
    })

    it('documents check:ci gate in package scripts (8.7 prerequisite)', () => {
      const packageJson = JSON.parse(readFileSync(resolve(FRONTEND_SRC, '../package.json'), 'utf8')) as {
        scripts: Record<string, string>
      }
      expect(packageJson.scripts['check:ci']).toContain('npm run check')
      expect(packageJson.scripts['check:ci']).toContain('npm run test')
    })
  })
})
