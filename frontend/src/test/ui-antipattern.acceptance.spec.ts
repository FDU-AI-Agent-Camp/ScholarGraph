/**
 * ui-design-progress §1.3 — 反模式清单自动化自查（Phase 8 全站复核）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'
import packageJson from '../../package.json'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const FORBIDDEN_MARKETING_COPY = [
  '卓越的用户体验',
  '卓越',
  '赋能',
  '一站式',
  '一体化解决方案',
  '极致',
  '无缝',
  '助力',
  '打造',
  'Lorem',
  'Lorem ipsum',
  'TODO 文案',
] as const

const FORBIDDEN_PLACEHOLDERS = ['请输入内容', '请输入…', '请输入问题', '请输入您的', 'placeholder="请输入"'] as const

const FORBIDDEN_PASSIVE_PATTERNS = [
  '可通过本区域完成',
  '可以通过本区域',
  '论文的上传可通过',
  '功能可通过',
  '将被自动',
] as const

const TAILWIND_DEFAULT_COLOR_TOKENS = [
  'bg-blue-',
  'text-blue-',
  'from-purple-',
  'to-indigo-',
  'bg-gradient-to-',
] as const

const FORBIDDEN_NAV_EMOJI = ['📄', '📁', '🔍', '✨', '🎯', '🚀', '💡', '📊', '📝'] as const

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

function collectTsFiles(relativeDir: string): string[] {
  const absoluteDir = resolve(FRONTEND_SRC, relativeDir)
  const files: string[] = []

  for (const entry of readdirSync(absoluteDir)) {
    const fullPath = join(absoluteDir, entry)
    if (statSync(fullPath).isDirectory()) {
      files.push(...collectTsFiles(join(relativeDir, entry)))
    } else if (entry.endsWith('.ts') && !entry.endsWith('.spec.ts') && !entry.endsWith('.test.ts')) {
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

function extractTemplateBlocks(src: string): string {
  return src.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '')
}

const homeViewSrc = readFrontendSource('views/HomeView.vue')
const appLayoutSrc = readFrontendSource('components/layout/AppLayout.vue')
const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')
const tokensCss = readSrc('styles/tokens.css')
const elementThemeSrc = readSrc('styles/element-theme.scss')
const typographyCss = readSrc('styles/typography.css')

const vueUiSources = [...collectVueFiles('views'), ...collectVueFiles('components')]

describe('§1.3 Anti-pattern checklist (full audit)', () => {
  describe('视觉 / 布局', () => {
    it('无 Inter 字体栈 + 无紫/蓝渐变主色', () => {
      const tokens = loadDesignTokenMap()

      expect(tokensCss.toLowerCase()).not.toContain("'inter'")
      expect(typographyCss.toLowerCase()).not.toContain("'inter'")
      expect(elementThemeSrc.toLowerCase()).not.toContain('inter')
      expect(tokens['--color-primary']).toBe('#0d6e6e')
      expect(tokensCss).not.toMatch(/linear-gradient|radial-gradient/i)
      expect(homeViewSrc).not.toMatch(/linear-gradient|radial-gradient/i)
    })

    it('无居中 Hero + 三等分卡片（Home 58/42 + 双 quick-card）', () => {
      expect(homeViewSrc).toContain('grid-template-columns: 58fr 42fr')
      expect(homeViewSrc).not.toContain('grid-template-columns: 1fr 1fr 1fr')
      expect(homeViewSrc).not.toMatch(/repeat\(3,\s*1fr\)/)
      expect(homeViewSrc).toContain('home-quick-links')
      expect(homeViewSrc.match(/class="home-quick-card"/g)?.length ?? 0).toBe(2)
    })

    it('导航/功能图标使用 Element Plus icon 组件，不用 Emoji', () => {
      expect(appLayoutSrc).toContain('<el-icon')
      expect(appLayoutSrc).toContain('HomeFilled')
      expect(appLayoutSrc).toContain('Document')
      expect(appLayoutSrc).toContain('Search')

      for (const emoji of FORBIDDEN_NAV_EMOJI) {
        expect(appLayoutSrc).not.toContain(emoji)
        expect(homeViewSrc).not.toContain(emoji)
      }
    })

    it('HSS/STEM Badge 除颜色外必有文字标签', () => {
      const badgeSrc = readFrontendSource('components/ui/BadgeParadigm.vue')
      expect(badgeSrc).toContain("return 'HSS'")
      expect(badgeSrc).toContain("return 'STEM'")
      expect(badgeSrc).toContain("return '未知'")
      expect(mount(BadgeParadigm, { props: { paradigm: 'HSS' } }).text()).toBe('HSS')
      expect(mount(BadgeParadigm, { props: { paradigm: 'STEM' } }).text()).toBe('STEM')
      expect(mount(BadgeParadigm, { props: { paradigm: null } }).text()).toBe('未知')
    })

    it('无 Tailwind 依赖与默认色板 class 直用', () => {
      expect(packageJson.dependencies).not.toHaveProperty('tailwindcss')
      expect(packageJson.devDependencies).not.toHaveProperty('tailwindcss')

      for (const relativePath of vueUiSources) {
        const template = extractTemplateBlocks(readSrc(relativePath))
        for (const token of TAILWIND_DEFAULT_COLOR_TOKENS) {
          expect(template, `${relativePath} must not use ${token}`).not.toContain(token)
        }
      }
    })

    it('无 EP 默认蓝 #409eff / 链接 #1a56db 残留', () => {
      const styleSources = [
        ...vueUiSources.map((file) => extractStyleBlocks(readSrc(file))),
        tokensCss,
        elementThemeSrc,
      ].join('\n')

      expect(styleSources.toLowerCase()).not.toContain('#409eff')
      expect(styleSources.toLowerCase()).not.toContain('#1a56db')
    })

    it('无整页单一纯色铺满（主视图引用分层 bg token）', () => {
      const mainViews = [
        'views/HomeView.vue',
        'views/PapersView.vue',
        'views/PaperDetailView.vue',
        'views/PaperGraphView.vue',
        'views/PatrolView.vue',
        'components/layout/AppLayout.vue',
      ]

      for (const viewPath of mainViews) {
        const src = readSrc(viewPath)
        const style = extractStyleBlocks(src)
        const hasLayeredBg =
          src.includes('var(--color-bg-page)') ||
          src.includes('var(--color-bg-surface)') ||
          src.includes('var(--color-bg-canvas)') ||
          src.includes('var(--color-bg-subtle)')
        expect(hasLayeredBg, viewPath).toBe(true)
        expect(style.match(/background:\s*#(?:fff|ffffff|f8f9fb)\s*;/gi) ?? [], viewPath).toEqual([])
      }
    })
  })

  describe('动效', () => {
    const styleSources = [...vueUiSources.map((file) => extractStyleBlocks(readSrc(file))), tokensCss, typographyCss]

    it('无裸 transition: all', () => {
      for (const style of styleSources) {
        expect(style).not.toMatch(/transition:\s*all/i)
      }
    })

    it('无 ease-in-out 作为 CSS 缓动默认', () => {
      for (const style of styleSources) {
        expect(style).not.toMatch(/ease-in-out/i)
      }
      expect(tokensCss).toContain('--ease-out-product')
    })

    it('图谱节点 hover 禁止位移（仅 stroke / lineWidth / fill 动画）', () => {
      expect(paperGraphUtilSrc).toContain('hover-activate')
      expect(paperGraphUtilSrc).toContain("fields: ['stroke', 'lineWidth', 'fill']")
      expect(paperGraphUtilSrc).toContain('buildG6Behaviors')
      expect(paperGraphUtilSrc).not.toMatch(/translate[XY]?|scale\s*:|transform\s*:/i)
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\./)
      expect(readFrontendSource('utils/paperGraph.test.ts')).toContain(
        'buildG6Behaviors + node animation avoid hover displacement',
      )
    })
  })

  describe('文案', () => {
    const copySources = [
      ...vueUiSources.map((file) => extractTemplateBlocks(readSrc(file))),
      ...collectTsFiles('constants').map((file) => readSrc(file)),
    ]

    it('无 Lorem / 空 placeholder 类文案', () => {
      for (const src of copySources) {
        for (const phrase of FORBIDDEN_PLACEHOLDERS) {
          expect(src).not.toContain(phrase)
        }
      }
      expect(readFrontendSource('constants/detailCopy.ts')).toContain('核心论点')
    })

    it('无产品黑话（§1.4.4 禁止词表）', () => {
      for (const src of copySources) {
        for (const word of FORBIDDEN_MARKETING_COPY) {
          expect(src, `found forbidden copy "${word}"`).not.toContain(word)
        }
      }
    })

    it('无被动语态脚手架长句', () => {
      for (const src of copySources) {
        for (const pattern of FORBIDDEN_PASSIVE_PATTERNS) {
          expect(src, `found passive pattern "${pattern}"`).not.toContain(pattern)
        }
      }
      expect(readFrontendSource('components/papers/PaperUpload.vue')).toContain('PAPERS_BASELINE_COPY')
      expect(readFrontendSource('constants/papersCopy.ts')).toContain('拖拽 PDF 到此处')
    })
  })
})
