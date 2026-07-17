/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** ui-design-progress §1.5 design parameter quick reference. */
export const DESIGN_CANVAS_BASE = { width: 1440, height: 900 } as const

export const DESIGN_CONTENT_MAX_WIDTH = '1280px'

export const DESIGN_SHELL_DIMENSIONS = {
  asideWidth: '240px',
  headerHeight: '56px',
} as const

export const DESIGN_CITATION_ACTIVE_HEX = '#e11d48'

export const DESIGN_CITATION_SYNC_MS = 150

/** ui-design-progress §1.2 core design decisions (design-spec §1). */
export const CORE_DESIGN_DECISIONS = {
  homeTypography: 'Serif display on Home hero only',
  innerTypography: 'Sans on workbench pages',
  primaryHex: '#0d6e6e',
  themeMode: 'light-only V1',
  detailLayout: 'QA left + graph right dual column from 1024px',
  componentLibrary: 'Element Plus deep-themed via element-theme.scss',
  graphNodeShape: 'uniform rounded rect',
  focusPages: ['Home', 'Detail', 'Graph'] as const,
  devicePriority: 'Desktop 1440 first',
} as const

export function tokensMatchDesignParams(tokens: Record<string, string>): boolean {
  return (
    tokens['--content-max-width'] === DESIGN_CONTENT_MAX_WIDTH &&
    tokens['--color-primary'] === CORE_DESIGN_DECISIONS.primaryHex &&
    tokens['--color-citation-active'] === DESIGN_CITATION_ACTIVE_HEX &&
    tokens['--duration-fast'] === `${DESIGN_CITATION_SYNC_MS}ms`
  )
}

export function shellDimensionsMatch(appLayoutSrc: string): boolean {
  return (
    appLayoutSrc.includes(`width="${DESIGN_SHELL_DIMENSIONS.asideWidth}"`) &&
    appLayoutSrc.includes(`height: ${DESIGN_SHELL_DIMENSIONS.headerHeight}`)
  )
}

export function citationActiveWiringMatches(options: {
  tokensCss: string
  tagCitationSrc: string
  paperGraphSrc: string
}): boolean {
  return (
    options.tokensCss.includes(`--color-citation-active: ${DESIGN_CITATION_ACTIVE_HEX}`) &&
    options.tagCitationSrc.includes('var(--color-citation-active)') &&
    options.paperGraphSrc.includes("'--color-citation-active'") &&
    options.paperGraphSrc.includes('GRAPH_STATE_ANIMATION_MS')
  )
}

export function homeUsesSerifInnerUsesSans(
  typographyCss: string,
  homeViewSrc: string,
  innerWorkbenchViewSrc: string,
): boolean {
  return (
    typographyCss.includes('.text-display') &&
    typographyCss.match(/\.text-display[\s\S]*font-family: var\(--font-serif\)/) !== null &&
    typographyCss.match(/\.text-h1[\s\S]*font-family: var\(--font-sans\)/) !== null &&
    homeViewSrc.includes('text-display') &&
    innerWorkbenchViewSrc.includes('text-h1')
  )
}

export function elementPlusDeepThemed(mainTsSrc: string, elementThemeSrc: string): boolean {
  return (
    mainTsSrc.includes('@/styles/element-theme.scss') &&
    elementThemeSrc.includes("'base': #0d6e6e") &&
    elementThemeSrc.includes("@forward 'element-plus/theme-chalk")
  )
}

export function detailDualColumnFrom1024(detailViewSrc: string): boolean {
  return (
    detailViewSrc.includes('@media (min-width: 1024px)') && detailViewSrc.includes('grid-template-columns: 45fr 55fr')
  )
}

export function graphUsesRoundedRectNodes(paperGraphSrc: string): boolean {
  return paperGraphSrc.includes("type: 'rect'") && paperGraphSrc.includes('GRAPH_NODE_RADIUS')
}

export function v1LightThemeOnly(tokensCss: string): boolean {
  return (
    tokensCss.includes('--color-bg-page:') &&
    !tokensCss.includes('prefers-color-scheme: dark') &&
    !tokensCss.includes('[data-theme="dark"]')
  )
}
