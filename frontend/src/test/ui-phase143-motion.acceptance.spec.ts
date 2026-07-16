/**
 * ui-design-progress §1.4.3 — 动效与交互（时长 / 缓动 / reduced-motion / focus-visible）
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { loadDesignTokenMap } from '@/test/helpers/designTokens'
import {
  declaresReducedMotionGuard,
  demoMotionDoesNotObstructReading,
  extractStyleBlocks,
  graphMotionBudgetWithinCitationFastMs,
  hasNoEaseInOutDefault,
  hasNoTransitionAll,
  MOTION_DURATION_TOKENS,
  MOTION_EASE_TOKENS,
  MOTION_TRANSITION_SHORTHANDS,
  REDUCED_MOTION_ANIMATION_SOURCES,
  usesExplicitTransitionProperties,
  usesSynchronousHighlightHandlers,
} from '@/test/helpers/motionDiscipline'
import { GRAPH_STATE_ANIMATION_MS } from '@/utils/paperGraph'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

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

describe('§1.4.3 Motion & interaction discipline', () => {
  const tokens = loadDesignTokenMap()
  const tokensCss = readSrc('styles/tokens.css')

  describe('全局动效 Token', () => {
    it('tokens.css defines §1.4.3 durations and ease curves', () => {
      expect(tokensCss).toContain('§1.4.3')
      expect(tokens['--duration-instant']).toBe('120ms')
      expect(tokens['--duration-fast']).toBe('150ms')
      expect(tokens['--duration-normal']).toBe('200ms')
      expect(tokens['--duration-slow']).toBe('250ms')
      expect(tokens['--duration-pulse']).toBe('1.5s')
      expect(tokens['--duration-blink']).toBe('1s')
      for (const name of MOTION_EASE_TOKENS) {
        expect(tokens[name]).toBeTruthy()
      }
      for (const name of MOTION_TRANSITION_SHORTHANDS) {
        expect(tokensCss).toContain(`${name}:`)
      }
    })

    it('reduced-motion block zeros durations while keeping color feedback instant', () => {
      const reduceBlock = tokensCss.match(/@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\}/)?.[1] ?? ''
      for (const name of MOTION_DURATION_TOKENS) {
        expect(reduceBlock).toContain(`${name}: 0ms`)
      }
      expect(reduceBlock).toContain('color feedback stays instant')
    })
  })

  describe('场景 × 时长 × 属性', () => {
    it('Nav / 按钮 hover — 120ms explicit background/border/color', () => {
      const appLayoutStyles = extractStyleBlocks(readSrc('components/layout/AppLayout.vue'))
      expect(appLayoutStyles).toContain('var(--transition-instant)')
      expect(appLayoutStyles).not.toMatch(/scale\s*\(/)
    })

    it('表格行 hover — 120ms background-color only', () => {
      const papersStyles = extractStyleBlocks(readSrc('views/PapersView.vue'))
      expect(papersStyles).toContain('transition: background-color var(--transition-instant)')
      expect(papersStyles).not.toMatch(/height:\s*\d+px.*transition/i)
    })

    it('Citation Tag ↔ Graph — 150ms fast token + shared highlightNodeId', () => {
      const tagSrc = readSrc('components/ui/TagCitation.vue')
      const detailSrc = readSrc('views/PaperDetailView.vue')
      expect(tagSrc).toContain('var(--transition-fast)')
      expect(detailSrc).toContain("item.type === 'node' && item.node_id === highlightNodeId")
      expect(detailSrc).toContain(':highlight-node-id="highlightNodeId"')
      expect(tokens['--duration-fast']).toBe('150ms')
    })

    it('Graph 节点 hover/active — 120ms stroke fields, no translate/scale', () => {
      const paperGraphSrc = readSrc('utils/paperGraph.ts')
      expect(paperGraphSrc).toContain(`duration: GRAPH_STATE_ANIMATION_MS`)
      expect(GRAPH_STATE_ANIMATION_MS).toBe(120)
      expect(paperGraphSrc).not.toMatch(/translate|scale|shadowBlur.*hover/i)
      expect(paperGraphSrc).toContain("fields: ['stroke', 'lineWidth', 'fill']")
    })

    it('路由 fade — 200ms opacity + translateY(8px)', () => {
      const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
      expect(appLayoutSrc).toContain('name="route-fade"')
      expect(appLayoutSrc).toContain('opacity var(--duration-normal)')
      expect(appLayoutSrc).toContain('translateY(8px)')
    })

    it('Pipeline Step 完成 — 250ms check-in; processing 1.5s pulse', () => {
      const statusSrc = readSrc('components/papers/PaperStatusPanel.vue')
      expect(statusSrc).toContain('status-step-check-in')
      expect(statusSrc).toContain('var(--duration-slow)')
      expect(statusSrc).toContain('status-step-pulse')
      expect(statusSrc).toContain('var(--duration-pulse)')
      expect(statusSrc).toContain('var(--ease-in-subtle)')
    })

    it('SSE 答案光标 — 1s step-end blink on opacity only', () => {
      const detailStyles = extractStyleBlocks(readSrc('views/PaperDetailView.vue'))
      expect(detailStyles).toContain('detail-qa-cursor-blink')
      expect(detailStyles).toContain('var(--duration-blink) step-end')
      expect(detailStyles).toMatch(/detail-qa__cursor[\s\S]*animation: detail-qa-cursor-blink/)
    })

    it('Upload drag-over — 120ms border/background', () => {
      const uploadSrc = readSrc('components/papers/PaperUpload.vue')
      expect(uploadSrc).toContain('var(--transition-instant)')
      expect(uploadSrc).toContain('border-color var(--transition-instant)')
    })

    it('Drawer 打开 — 250ms transform translate', () => {
      const drawerStyles = extractStyleBlocks(readSrc('components/graph/GraphNodeDrawer.vue'))
      expect(drawerStyles).toContain('transition: transform var(--transition-slow)')
    })
  })

  describe('无障碍 — focus-visible 与 reduced-motion', () => {
    it('main.css exposes 2px primary focus-visible ring for links and buttons', () => {
      const mainCss = readSrc('assets/main.css')
      expect(mainCss).toContain(':focus-visible')
      expect(mainCss).toContain('outline: 2px solid var(--color-primary)')
      expect(mainCss).toContain('outline-offset: 2px')
    })

    it('animation sources declare prefers-reduced-motion guards', () => {
      for (const path of REDUCED_MOTION_ANIMATION_SOURCES) {
        const src = readSrc(path)
        expect(declaresReducedMotionGuard(src), path).toBe(true)
      }
    })

    it('route-fade and drawer slide disabled under reduced motion', () => {
      const appLayoutSrc = readSrc('components/layout/AppLayout.vue')
      expect(appLayoutSrc).toContain('.route-fade-enter-active')
      expect(appLayoutSrc).toMatch(/prefers-reduced-motion: reduce[\s\S]*transition:\s*none/)

      const drawerSrc = readSrc('components/graph/GraphNodeDrawer.vue')
      expect(drawerSrc).toMatch(/prefers-reduced-motion: reduce[\s\S]*transition:\s*none/)
    })
  })

  describe('§1.4.3 动效验收 — checklist', () => {
    it('Citation 点击后 Tag 与节点同一帧内开始变化，150ms 内完成', () => {
      const detailSrc = readSrc('views/PaperDetailView.vue')
      const qaComposableSrc = readSrc('composables/usePaperDetailQa.ts')
      expect(usesSynchronousHighlightHandlers(qaComposableSrc)).toBe(true)
      expect(detailSrc).toContain("item.type === 'node' && item.node_id === highlightNodeId")
      expect(detailSrc).toContain(':highlight-node-id="highlightNodeId"')
      expect(readSrc('components/ui/TagCitation.vue')).toContain('var(--transition-fast)')
      expect(graphMotionBudgetWithinCitationFastMs(GRAPH_STATE_ANIMATION_MS, 150)).toBe(true)
      expect(tokens['--duration-fast']).toBe('150ms')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('wires Detail view citation click')
      expect(readSrc('views/PaperDetailView.spec.ts')).toContain('§1.4.3 citation ↔ graph highlight')
    })

    it('无任何 transition: all', () => {
      const styleSources = [
        ...collectVueFiles('views'),
        ...collectVueFiles('components'),
        'styles/tokens.css',
        'assets/main.css',
      ]

      for (const relativePath of styleSources) {
        const styleSrc =
          relativePath.endsWith('.css') || relativePath.endsWith('.scss')
            ? readSrc(relativePath)
            : extractStyleBlocks(readSrc(relativePath))
        expect(hasNoTransitionAll(styleSrc), relativePath).toBe(true)
        expect(hasNoEaseInOutDefault(styleSrc), relativePath).toBe(true)
        expect(usesExplicitTransitionProperties(styleSrc), relativePath).toBe(true)
      }
      expect(readSrc('test/ui-antipattern.acceptance.spec.ts')).toContain('无裸 transition: all')
    })

    it('演示时动效不遮挡 SSE 阅读与图谱节点 label', () => {
      const detailStyles = extractStyleBlocks(readSrc('views/PaperDetailView.vue'))
      const paperGraphSrc = readSrc('utils/paperGraph.ts')
      const appLayoutSrc = readSrc('components/layout/AppLayout.vue')

      expect(demoMotionDoesNotObstructReading(detailStyles, paperGraphSrc, readSrc('views/PaperDetailView.vue'))).toBe(
        true,
      )
      expect(appLayoutSrc).not.toMatch(/blur\s*\(/i)
      expect(readSrc('views/PaperDetailView.vue')).toContain('class="detail-qa__answer-text"')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.3 动效验收 checklist')
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.3 motion acceptance checklist')
    })

    it('registers graph-qa and demo-path integration gates for defense motion path', () => {
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('keeps TagCitation active transition within 150ms')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('必测交互：Citation Tag click')
    })
  })
})
