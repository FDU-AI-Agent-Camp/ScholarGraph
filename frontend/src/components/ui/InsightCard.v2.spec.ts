/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Unit / interface — Part F / F4: V2 left-border variants on production InsightCard.
 *
 * Class binding is exercised via mount (runtime). Accent colors cannot be read via
 * getComputedStyle under happy-dom scoped CSS, so border contracts assert the
 * production SFC stylesheet the same way ui.spec.ts already locks V1 accents.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { PatrolMode } from '@/api/types'
import InsightCard from '@/components/ui/InsightCard.vue'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'

const V2_MODES = ['method_overlap', 'claim_evolution'] as const satisfies readonly PatrolMode[]

describe('InsightCard V2 variants (F4 unit)', () => {
  it.each(V2_MODES)('applies insight-card--%s from variant prop at runtime', (mode) => {
    const wrapper = mount(InsightCard, {
      props: { variant: mode, title: `title-${mode}`, summary: 'summary' },
    })

    expect(wrapper.classes()).toContain(`insight-card--${mode}`)
    expect(wrapper.find('.insight-card__title').text()).toBe(`title-${mode}`)
  })

  it('stylesheet defines V2 left borders using design tokens (production CSS)', () => {
    const src = readFrontendSource('components/ui/InsightCard.vue')
    const tokens = loadDesignTokenMap()

    expect(src).toMatch(/\.insight-card--method_overlap\s*\{[^}]*border-left:\s*4px\s+solid\s+var\(--color-info\)/)
    expect(src).toMatch(/\.insight-card--claim_evolution\s*\{[^}]*border-left:\s*4px\s+solid\s+var\(--color-success\)/)
    expect(tokens['--color-info']).toBe('#2563eb')
    expect(tokens['--color-success']).toBe('#059669')
  })
})
