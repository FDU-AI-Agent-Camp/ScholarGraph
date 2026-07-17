/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** ui-design-progress §1.4.3 motion token names from tokens.css */
export const MOTION_DURATION_TOKENS = [
  '--duration-instant',
  '--duration-fast',
  '--duration-normal',
  '--duration-slow',
  '--duration-pulse',
  '--duration-blink',
] as const

export const MOTION_EASE_TOKENS = ['--ease-out-product', '--ease-in-subtle'] as const

export const MOTION_TRANSITION_SHORTHANDS = [
  '--transition-instant',
  '--transition-fast',
  '--transition-normal',
  '--transition-slow',
] as const

/** Vue SFC sources expected to declare local prefers-reduced-motion overrides when animating. */
export const REDUCED_MOTION_ANIMATION_SOURCES = [
  'components/layout/AppLayout.vue',
  'components/ui/BadgeStatus.vue',
  'components/papers/PaperStatusPanel.vue',
  'components/graph/GraphNodeDrawer.vue',
  'views/PaperDetailView.vue',
] as const

export function extractStyleBlocks(src: string): string {
  return [...src.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)].map((match) => match[1] ?? '').join('\n')
}

function stripCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

export function hasNoTransitionAll(styleSrc: string): boolean {
  return !/transition\s*:\s*all\b/i.test(stripCssComments(styleSrc))
}

export function hasNoEaseInOutDefault(styleSrc: string): boolean {
  return !/\bease-in-out\b/i.test(stripCssComments(styleSrc))
}

export function declaresReducedMotionGuard(styleSrc: string): boolean {
  return styleSrc.includes('@media (prefers-reduced-motion: reduce)')
}

export function usesExplicitTransitionProperties(styleSrc: string): boolean {
  const blocks = [...styleSrc.matchAll(/transition\s*:\s*([^;]+);/gi)].map((match) => match[1] ?? '')
  if (blocks.length === 0) {
    return true
  }
  return blocks.every((block) => !/^\s*all\s/i.test(block.trim()))
}

/** Detail handlers assign highlightNodeId synchronously (same-frame Tag + graph react). */
export function usesSynchronousHighlightHandlers(scriptSrc: string): boolean {
  return (
    /function focusCitation[\s\S]*?highlightNodeId\.value\s*=\s*citation\.node_id/.test(scriptSrc) &&
    /function onGraphNodeClick[\s\S]*?highlightNodeId\.value\s*=\s*nodeId/.test(scriptSrc) &&
    !/function focusCitation[\s\S]*?await/.test(scriptSrc) &&
    !/function onGraphNodeClick[\s\S]*?await/.test(scriptSrc)
  )
}

export function graphMotionBudgetWithinCitationFastMs(graphStateAnimationMs: number, durationFastMs: number): boolean {
  return graphStateAnimationMs <= durationFastMs
}

export function extractAnswerPanelStyleBlock(styleSrc: string): string {
  return styleSrc.match(/\.detail-qa__answer-panel\s*\{[^}]*\}/)?.[0] ?? ''
}

/** Answer panel itself must stay static; cursor blink lives on `.detail-qa__cursor` only. */
export function answerPanelStyleBlockHasNoAnimation(styleSrc: string): boolean {
  const block = extractAnswerPanelStyleBlock(styleSrc)
  return block.length > 0 && !/\banimation\b/i.test(block)
}

/** Demo/SSE path: no animation on answer panel; graph labels use labelFill without hover translate. */
export function demoMotionDoesNotObstructReading(
  detailStyleSrc: string,
  paperGraphUtilSrc: string,
  detailViewSrc = '',
): boolean {
  const answerPanelBlock = extractAnswerPanelStyleBlock(detailStyleSrc)
  const hasReadableAnswerSurface =
    (answerPanelBlock.includes('color:') && answerPanelBlock.includes('white-space')) ||
    detailViewSrc.includes('text-body-lg') ||
    detailViewSrc.includes('detail-qa__answer-text')
  const answerPanelNotAnimated = answerPanelStyleBlockHasNoAnimation(detailStyleSrc)
  const cursorOpacityOnly = /\.detail-qa__cursor[\s\S]*animation:\s*detail-qa-cursor-blink/.test(detailStyleSrc)
  const labelsBound = paperGraphUtilSrc.includes('labelFill')
  const noHoverTranslate = !/\btranslate\s*\(/i.test(paperGraphUtilSrc)

  return hasReadableAnswerSurface && answerPanelNotAnimated && cursorOpacityOnly && labelsBound && noHoverTranslate
}
