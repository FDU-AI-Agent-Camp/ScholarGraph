/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** ui-design-progress §1.4.2 spacing scale — only these px values for margin/padding/gap. */
export const SPACING_SCALE_PX = [4, 8, 12, 16, 24, 32, 48, 64] as const

export const SPACING_TOKEN_NAMES = [
  '--spacing-4',
  '--spacing-8',
  '--spacing-12',
  '--spacing-16',
  '--spacing-24',
  '--spacing-32',
  '--spacing-48',
  '--spacing-64',
] as const

/** Files allowed to use off-scale px for component chrome (stepper glyph, EP tag micro-padding). */
export const LAYOUT_MICRO_PX_ALLOWLIST = [
  'components/layout/AppLayout.vue',
  'components/papers/PaperStatusPanel.vue',
] as const

/** Workbench surfaces scanned for table / stepper / form grid alignment. */
export const WORKBENCH_LAYOUT_FILES = [
  'views/PapersView.vue',
  'views/PaperDetailView.vue',
  'components/papers/PaperStatusPanel.vue',
  'components/papers/PaperUpload.vue',
  'views/PatrolView.vue',
] as const

export function extractVueTemplate(src: string): string {
  return src.match(/<template>([\s\S]*?)<\/template>/)?.[1] ?? ''
}

export function extractStyleBlocks(src: string): string {
  return [...src.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((match) => match[1] ?? '').join('\n')
}

export function countHeadingLevel(src: string, level: 1 | 2 | 3): number {
  const template = extractVueTemplate(src)
  const pattern = new RegExp(`<h${level}\\b`, 'gi')
  return [...template.matchAll(pattern)].length
}

/** Raw font-size: Npx in scoped styles — views should prefer typography utilities or var(--text-*). */
export function listRawFontSizePx(styleSrc: string): string[] {
  return [...styleSrc.matchAll(/font-size:\s*(\d+)px/gi)].map((match) => match[1] ?? '')
}

/** Collect off-scale px values from margin/padding/gap declarations. */
export function listOffScaleSpacingPxValues(styleSrc: string, allowMicroPx: boolean): number[] {
  const offenders: number[] = []
  const spacingProps = [...styleSrc.matchAll(/(?:margin|padding|gap)(?:-[a-z]+)?:\s*([^;]+);/gi)]

  for (const match of spacingProps) {
    const value = match[1]?.trim() ?? ''
    if (value.includes('var(--spacing-')) {
      continue
    }
    const pxValues = [...value.matchAll(/(\d+)px/g)].map((pxMatch) => Number(pxMatch[1]))
    for (const px of pxValues) {
      if ((SPACING_SCALE_PX as readonly number[]).includes(px)) {
        continue
      }
      if (allowMicroPx && (px === 2 || px === 0)) {
        continue
      }
      offenders.push(px)
    }
  }

  return offenders
}

export function hasNoOffScaleMarginTop(styleSrc: string, allowMicroPx = true): boolean {
  const marginTopProps = [...styleSrc.matchAll(/margin-top:\s*([^;]+);/gi)]
  for (const match of marginTopProps) {
    const value = match[1]?.trim() ?? ''
    if (value.includes('var(--spacing-')) {
      continue
    }
    const pxValues = [...value.matchAll(/(\d+)px/g)].map((pxMatch) => Number(pxMatch[1]))
    for (const px of pxValues) {
      if (!(SPACING_SCALE_PX as readonly number[]).includes(px)) {
        if (allowMicroPx && (px === 2 || px === 0)) {
          continue
        }
        return false
      }
    }
  }
  return true
}

export function usesOnlySpacingTokensOrAllowlistedPx(styleSrc: string, allowMicroPx: boolean): boolean {
  return listOffScaleSpacingPxValues(styleSrc, allowMicroPx).length === 0
}
