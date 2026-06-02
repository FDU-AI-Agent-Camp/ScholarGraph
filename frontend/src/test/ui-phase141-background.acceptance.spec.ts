/**
 * ui-design-progress §1.4.1 — 背景与色彩（学术工作台三层体系 + 对比度验收）
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { contrastRatio, WCAG_AA_TEXT_CONTRAST, WCAG_AA_UI_CONTRAST } from '@/test/helpers/colorContrast'
import { loadDesignTokenMap } from '@/test/helpers/designTokens'
import {
  getGraphNodeFillColor,
  getGraphNodeTypeColor,
  listGraphNodeTypeStrokeColors,
  GRAPH_NODE_SHADOW_BLUR,
  GRAPH_NODE_SURFACE_FILL,
} from '@/utils/paperGraph'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const CARD_SURFACE_FILES = [
  'views/HomeView.vue',
  'components/papers/PaperMetadataCard.vue',
  'components/papers/PaperStatusPanel.vue',
  'components/ui/InsightCard.vue',
  'assets/main.css',
] as const

const SEMANTIC_COLOR_ALLOWLIST = [
  'components/ui/BadgeStatus.vue',
  'components/papers/PaperStatusPanel.vue',
  'components/ui/InsightCard.vue',
  'components/ui/BadgeParadigm.vue',
  'styles/tokens.css',
  'styles/element-theme.scss',
] as const

function readSrc(relativePathFromSrc: string): string {
  return readFileSync(resolve(FRONTEND_SRC, relativePathFromSrc), 'utf8')
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

function extractStyleBlocks(src: string): string {
  return [...src.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((match) => match[1] ?? '').join('\n')
}

function isSemanticColorAllowlisted(relativePath: string): boolean {
  return (SEMANTIC_COLOR_ALLOWLIST as readonly string[]).includes(relativePath)
}

describe('§1.4.1 Background & color discipline', () => {
  const tokens = loadDesignTokenMap()

  describe('三层背景 Token 落地', () => {
    it('tokens.css defines page / surface / canvas / subtle layers with design-spec hex', () => {
      expect(tokens['--color-bg-page']).toBe('#f8f9fb')
      expect(tokens['--color-bg-surface']).toBe('#ffffff')
      expect(tokens['--color-bg-canvas']).toBe('#f1f5f9')
      expect(tokens['--color-bg-subtle']).toBe('#fafbfc')
      expect(tokens['--color-bg-page']).not.toBe(tokens['--color-bg-surface'])
      expect(tokens['--color-bg-canvas']).not.toBe(tokens['--color-bg-surface'])
    })

    it('App Shell separates surface sidebar/header from page main', () => {
      const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
      expect(appLayoutSrc).toContain('background: var(--color-bg-page)')
      expect(appLayoutSrc).toContain('background: var(--color-bg-surface)')
    })

    it('graph stage uses canvas + surface legend float layer', () => {
      expect(readSrc('components/graph/PaperGraph.vue')).toContain('var(--color-bg-canvas)')
      expect(readSrc('components/graph/GraphLegend.vue')).toContain('var(--color-bg-surface)')
      expect(readSrc('views/PaperGraphView.vue')).toContain('var(--color-bg-canvas)')
    })

    it('answer panel uses subtle inset inside QA card', () => {
      const detailSrc = readSrc('views/PaperDetailView.vue')
      expect(detailSrc).toContain('var(--color-bg-subtle)')
    })
  })

  describe('正文与图谱对比度验收', () => {
    it('正文 --color-text-primary 对 surface/page 对比度 ≥ 4.5:1', () => {
      const textPrimary = tokens['--color-text-primary'] ?? '#111827'
      const pageBg = tokens['--color-bg-page'] ?? '#f8f9fb'
      const surfaceBg = tokens['--color-bg-surface'] ?? '#ffffff'

      expect(contrastRatio(textPrimary, surfaceBg)).toBeGreaterThanOrEqual(WCAG_AA_TEXT_CONTRAST)
      expect(contrastRatio(textPrimary, pageBg)).toBeGreaterThanOrEqual(WCAG_AA_TEXT_CONTRAST)
    })

    it('图谱节点 surface fill + type stroke 与 canvas 对比度足够（stroke ≥ 3:1）', () => {
      const canvasBg = tokens['--color-bg-canvas'] ?? '#f1f5f9'
      const nodeFill = getGraphNodeFillColor('Thesis', 'HSS')

      expect(nodeFill).toBe(GRAPH_NODE_SURFACE_FILL)
      expect(contrastRatio(nodeFill, canvasBg)).toBeGreaterThan(1)

      for (const strokeColor of listGraphNodeTypeStrokeColors('HSS')) {
        expect(contrastRatio(strokeColor, canvasBg)).toBeGreaterThanOrEqual(WCAG_AA_UI_CONTRAST)
      }
      for (const strokeColor of listGraphNodeTypeStrokeColors('STEM')) {
        expect(contrastRatio(strokeColor, canvasBg)).toBeGreaterThanOrEqual(WCAG_AA_UI_CONTRAST)
      }
    })

    it('PaperGraph node style adds shadow depth so surface nodes do not blur into canvas', () => {
      const paperGraphUtilSrc = readSrc('utils/paperGraph.ts')
      expect(paperGraphUtilSrc).toContain('GRAPH_NODE_SHADOW_BLUR')
      expect(paperGraphUtilSrc).toContain('shadowBlur')
      expect(GRAPH_NODE_SHADOW_BLUR).toBeGreaterThan(0)
      expect(getGraphNodeTypeColor('Thesis', 'HSS')).toBe(tokens['--color-primary'])
    })
  })

  describe('强调色与分层手段', () => {
    it('主色不作视口级容器大底铺色（允许分段控件 active 等小面积）', () => {
      const rootPrimaryPattern =
        /\.(?:home|patrol-view|paper-detail|papers-view|graph-view)(?:__[\w-]+)?\s*\{[^}]*background(?:-color)?:[^;]*var\(--color-primary\)/gi

      for (const relativePath of collectVueFiles('views')) {
        const style = extractStyleBlocks(readSrc(relativePath))
        expect(style, relativePath).not.toMatch(rootPrimaryPattern)
      }
    })

    it.each(CARD_SURFACE_FILES)('%s uses card layering: border + shadow-sm + radius xl', (relativePath) => {
      const src = readSrc(relativePath)
      expect(src).toContain('var(--color-border)')
      expect(src).toContain('var(--shadow-sm)')
      expect(src).toContain('var(--radius-xl)')
    })

    it('semantic status tokens stay within badge/alert allowlist in views/components', () => {
      const vueFiles = [...collectVueFiles('views'), ...collectVueFiles('components')]
      const semanticPattern = /var\(--color-(success|warning|error|info)\)/

      for (const relativePath of vueFiles) {
        if (isSemanticColorAllowlisted(relativePath)) {
          continue
        }
        expect(readSrc(relativePath), relativePath).not.toMatch(semanticPattern)
      }
    })

    it('views avoid flat root hex backgrounds without layered bg tokens', () => {
      for (const relativePath of collectVueFiles('views')) {
        const src = readSrc(relativePath)
        const style = extractStyleBlocks(src)
        const hasLayeredBg =
          src.includes('var(--color-bg-page)') ||
          src.includes('var(--color-bg-surface)') ||
          src.includes('var(--color-bg-canvas)') ||
          src.includes('var(--color-bg-subtle)')
        expect(hasLayeredBg, relativePath).toBe(true)
        expect(style.match(/background:\s*#(?:fff|ffffff|f8f9fb)\s*;/gi) ?? [], relativePath).toEqual([])
      }
    })
  })
})

describe('colorContrast helper sanity', () => {
  it('computes known high-contrast pair for #111827 on #ffffff', () => {
    expect(contrastRatio('#111827', '#ffffff')).toBeGreaterThanOrEqual(15)
  })
})
