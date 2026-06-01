/**
 * ui-design-progress §1.2 核心设计决策 + §1.5 设计参数速查
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import {
  citationActiveWiringMatches,
  CORE_DESIGN_DECISIONS,
  DESIGN_CANVAS_BASE,
  DESIGN_CITATION_ACTIVE_HEX,
  DESIGN_CITATION_SYNC_MS,
  DESIGN_CONTENT_MAX_WIDTH,
  DESIGN_SHELL_DIMENSIONS,
  detailDualColumnFrom1024,
  elementPlusDeepThemed,
  graphUsesRoundedRectNodes,
  homeUsesSerifInnerUsesSans,
  shellDimensionsMatch,
  tokensMatchDesignParams,
  v1LightThemeOnly,
} from '@/test/helpers/designFoundationDiscipline'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import { GRAPH_STATE_ANIMATION_MS } from '@/utils/paperGraph'

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

function readDesignSpec(): string {
  return readFileSync(resolve(REPO_ROOT, 'docs/v1/design-spec.md'), 'utf8')
}

function readSrc(relativePathFromSrc: string): string {
  return readFrontendSource(relativePathFromSrc)
}

describe('§1.5 设计参数速查', () => {
  const tokens = loadDesignTokenMap()
  const tokensCss = readSrc('styles/tokens.css')
  const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
  const tagCitationSrc = readSrc('components/ui/TagCitation.vue')
  const paperGraphSrc = readSrc('utils/paperGraph.ts')

  it('画布基准 1440×900（design-spec §4）', () => {
    const designSpec = readDesignSpec()
    expect(designSpec).toContain('1440 × 900')
    expect(designSpec).toContain('1440×900')
    expect(DESIGN_CANVAS_BASE.width).toBe(1440)
    expect(DESIGN_CANVAS_BASE.height).toBe(900)
  })

  it('内容 max-width 1280px（§1.4.2）', () => {
    expect(tokens['--content-max-width']).toBe(DESIGN_CONTENT_MAX_WIDTH)
    expect(tokensCss).toContain('--content-max-width: 1280px')
    expect(readSrc('assets/main.css')).toContain('var(--content-max-width)')
  })

  it('侧栏 / 顶栏 240px / 56px（Phase 1 App Shell）', () => {
    expect(shellDimensionsMatch(appLayoutSrc)).toBe(true)
    expect(DESIGN_SHELL_DIMENSIONS.asideWidth).toBe('240px')
    expect(DESIGN_SHELL_DIMENSIONS.headerHeight).toBe('56px')
    expect(readSrc('test/ui-phase142-layout.acceptance.spec.ts')).toContain('--content-max-width: 1280px')
  })

  it('Citation active #E11D48（tokens + G6 + TagCitation）', () => {
    expect(tokensMatchDesignParams(tokens)).toBe(true)
    expect(tokens['--color-citation-active']).toBe(DESIGN_CITATION_ACTIVE_HEX)
    expect(citationActiveWiringMatches({ tokensCss, tagCitationSrc, paperGraphSrc })).toBe(true)
    expect(readSrc('test/ui-phase2.acceptance.spec.ts')).toContain('#e11d48')
  })

  it('答辩必测联动 Tag click ↔ node active 150ms（§6）', () => {
    expect(tokens['--duration-fast']).toBe(`${DESIGN_CITATION_SYNC_MS}ms`)
    expect(GRAPH_STATE_ANIMATION_MS).toBeLessThanOrEqual(DESIGN_CITATION_SYNC_MS)
    expect(readSrc('test/ui-phase143-motion.acceptance.spec.ts')).toContain('§1.4.3 动效验收 — checklist')
    expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.3 motion acceptance checklist')
    expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.3 动效验收 checklist')
    expect(readSrc('views/PaperDetailView.spec.ts')).toContain('§1.4.3 checklist')
  })
})

describe('§1.2 核心设计决策（design-spec §1）', () => {
  const tokensCss = readSrc('styles/tokens.css')
  const typographyCss = readSrc('styles/typography.css')
  const homeViewSrc = readSrc('views/HomeView.vue')
  const detailViewSrc = readSrc('views/PaperDetailView.vue')
  const paperGraphSrc = readSrc('utils/paperGraph.ts')
  const mainTsSrc = readSrc('main.ts')
  const elementThemeSrc = readSrc('styles/element-theme.scss')

  it('气质：Home Serif display，内页 Sans 标题', () => {
    expect(homeUsesSerifInnerUsesSans(typographyCss, homeViewSrc, readSrc('views/PapersView.vue'))).toBe(true)
    expect(CORE_DESIGN_DECISIONS.homeTypography).toContain('Serif')
  })

  it('主色：学术青 #0D6E6E', () => {
    expect(loadDesignTokenMap()['--color-primary']).toBe(CORE_DESIGN_DECISIONS.primaryHex)
    expect(tokensCss).toContain('--color-primary: #0d6e6e')
    expect(elementThemeSrc).toContain('#0d6e6e')
  })

  it('主题：V1 仅浅色', () => {
    expect(v1LightThemeOnly(tokensCss)).toBe(true)
    expect(CORE_DESIGN_DECISIONS.themeMode).toContain('light')
  })

  it('详情页：≥1024px 左 QA + 右图谱双栏', () => {
    expect(detailDualColumnFrom1024(detailViewSrc)).toBe(true)
    expect(detailViewSrc.indexOf('detail-main')).toBeLessThan(detailViewSrc.indexOf('detail-graph'))
  })

  it('组件库：Element Plus 深度定制', () => {
    expect(elementPlusDeepThemed(mainTsSrc, elementThemeSrc)).toBe(true)
  })

  it('图谱节点：统一圆角矩形', () => {
    expect(graphUsesRoundedRectNodes(paperGraphSrc)).toBe(true)
    expect(readSrc('test/ui-phase6-graph.acceptance.spec.ts')).toContain("type: 'rect'")
  })

  it('重点页：Home、Detail（Citation 联动）、Graph 路由可达', () => {
    const routeNames = routes.map((route) => route.name)
    expect(routeNames).toEqual(expect.arrayContaining([RouteName.Home, RouteName.PaperDetail, RouteName.PaperGraph]))
    expect(readSrc('test/demo-path.integration.test.ts')).toContain('design-spec §16 Prototype 答辩路径')
  })

  it('设备：Desktop 1440 优先（design-spec + 1280 内容区 + 响应式断点次要）', () => {
    const designSpec = readDesignSpec()
    expect(designSpec).toMatch(/Desktop.*1440|1440.*Desktop/i)
    expect(loadDesignTokenMap()['--content-max-width']).toBe('1280px')
    expect(readSrc('test/ui-phase8-responsive.acceptance.spec.ts')).toContain('@media (min-width: 1280px)')
  })
})
