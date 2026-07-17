/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Unit / interface — Part F / F4: V2 borders on production InsufficientDataInsightCard.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { PatrolMode } from '@/api/types'
import InsufficientDataInsightCard from '@/components/ui/InsufficientDataInsightCard.vue'
import { readFrontendSource } from '@/test/helpers/designTokens'

const V2_MODES = ['method_overlap', 'claim_evolution'] as const satisfies readonly PatrolMode[]

describe('InsufficientDataInsightCard V2 variants (F4 unit)', () => {
  it.each(V2_MODES)('applies insufficient-insight-card--%s at runtime from variant', (mode) => {
    const wrapper = mount(InsufficientDataInsightCard, {
      props: {
        variant: mode,
        title: '阴性标题',
        summary: 'summary',
        exclusionLogic: {
          phase: 'PARADIGM_GATE',
          reason_code: 'PARADIGM_UNSUPPORTED',
          description: 'desc',
        },
      },
    })

    expect(wrapper.classes()).toContain(`insufficient-insight-card--${mode}`)
    expect(wrapper.attributes('data-testid')).toBe('insufficient-data-insight-card')
  })

  it('stylesheet defines V2 left borders aligned with InsightCard tokens', () => {
    const src = readFrontendSource('components/ui/InsufficientDataInsightCard.vue')

    expect(src).toMatch(
      /\.insufficient-insight-card--method_overlap\s*\{[^}]*border-left:\s*4px\s+solid\s+var\(--color-info\)/,
    )
    expect(src).toMatch(
      /\.insufficient-insight-card--claim_evolution\s*\{[^}]*border-left:\s*4px\s+solid\s+var\(--color-success\)/,
    )
  })
})
