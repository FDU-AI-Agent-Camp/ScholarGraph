/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import {
  citationActiveWiringMatches,
  DESIGN_CITATION_ACTIVE_HEX,
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
import { loadDesignTokenMap } from '@/test/helpers/designTokens'

describe('designFoundationDiscipline helper', () => {
  it('tokensMatchDesignParams validates §1.5 token table', () => {
    const tokens = loadDesignTokenMap()
    expect(tokensMatchDesignParams(tokens)).toBe(true)
    expect(tokens['--content-max-width']).toBe(DESIGN_CONTENT_MAX_WIDTH)
    expect(tokens['--color-citation-active']).toBe(DESIGN_CITATION_ACTIVE_HEX)
  })

  it('shellDimensionsMatch checks 240px aside and 56px header', () => {
    const layout = `<el-aside width="${DESIGN_SHELL_DIMENSIONS.asideWidth}"><header style="height: 56px">`
    expect(shellDimensionsMatch(layout)).toBe(true)
  })

  it('citationActiveWiringMatches requires tokens + Tag + G6 util chain', () => {
    expect(
      citationActiveWiringMatches({
        tokensCss: '--color-citation-active: #e11d48;',
        tagCitationSrc: 'var(--color-citation-active)',
        paperGraphSrc: "'--color-citation-active' + GRAPH_STATE_ANIMATION_MS",
      }),
    ).toBe(true)
  })

  it('homeUsesSerifInnerUsesSans separates display vs h1 stacks', () => {
    const typography = `
.text-display { font-family: var(--font-serif); }
.text-h1 { font-family: var(--font-sans); }`
    const home = '<h1 class="text-display">'
    const papers = '<h1 class="text-h1 papers-title">'
    expect(homeUsesSerifInnerUsesSans(typography, home, papers)).toBe(true)
  })

  it('detailDualColumnFrom1024 and graphUsesRoundedRectNodes cover §1.2 layout/shape', () => {
    expect(detailDualColumnFrom1024('@media (min-width: 1024px) { grid-template-columns: 45fr 55fr; }')).toBe(true)
    expect(graphUsesRoundedRectNodes("type: 'rect' + GRAPH_NODE_RADIUS")).toBe(true)
  })

  it('elementPlusDeepThemed and v1LightThemeOnly cover EP + light V1', () => {
    expect(
      elementPlusDeepThemed(
        "import '@/styles/element-theme.scss'",
        "@forward 'element-plus/theme-chalk' with ( 'base': #0d6e6e )",
      ),
    ).toBe(true)
    expect(v1LightThemeOnly(':root { --color-bg-page: #f8f9fb; }')).toBe(true)
  })
})
