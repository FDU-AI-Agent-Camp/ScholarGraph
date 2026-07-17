/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import {
  answerPanelStyleBlockHasNoAnimation,
  demoMotionDoesNotObstructReading,
  extractStyleBlocks,
  graphMotionBudgetWithinCitationFastMs,
  hasNoEaseInOutDefault,
  hasNoTransitionAll,
  MOTION_DURATION_TOKENS,
  usesExplicitTransitionProperties,
  usesSynchronousHighlightHandlers,
} from '@/test/helpers/motionDiscipline'
import { GRAPH_STATE_ANIMATION_MS } from '@/utils/paperGraph'

describe('motionDiscipline helper', () => {
  it('MOTION_DURATION_TOKENS lists §1.4.3 durations', () => {
    expect(MOTION_DURATION_TOKENS).toContain('--duration-fast')
    expect(MOTION_DURATION_TOKENS).toContain('--duration-blink')
  })

  it('hasNoTransitionAll rejects transition: all', () => {
    expect(hasNoTransitionAll('.x { transition: all 120ms; }')).toBe(false)
    expect(hasNoTransitionAll('.x { transition: color var(--transition-instant); }')).toBe(true)
  })

  it('hasNoEaseInOutDefault rejects ease-in-out', () => {
    expect(hasNoEaseInOutDefault('transition: opacity 200ms ease-in-out;')).toBe(false)
    expect(hasNoEaseInOutDefault('transition: opacity var(--transition-normal);')).toBe(true)
  })

  it('usesExplicitTransitionProperties allows multi-property explicit lists', () => {
    const styles = extractStyleBlocks(`
<style scoped>
.btn {
  transition:
    background-color var(--transition-instant),
    border-color var(--transition-instant);
}
</style>`)
    expect(usesExplicitTransitionProperties(styles)).toBe(true)
  })

  it('usesSynchronousHighlightHandlers detects same-frame highlight assignment', () => {
    const script = `
function focusCitation(citation) {
  highlightNodeId.value = citation.node_id
}
function onGraphNodeClick(nodeId) {
  highlightNodeId.value = nodeId
}`
    expect(usesSynchronousHighlightHandlers(script)).toBe(true)
  })

  it('graphMotionBudgetWithinCitationFastMs requires graph stroke ≤150ms', () => {
    expect(graphMotionBudgetWithinCitationFastMs(GRAPH_STATE_ANIMATION_MS, 150)).toBe(true)
    expect(graphMotionBudgetWithinCitationFastMs(200, 150)).toBe(false)
  })

  it('answerPanelStyleBlockHasNoAnimation ignores cursor keyframes elsewhere in file', () => {
    const styles = extractStyleBlocks(`
<style scoped>
.detail-qa__answer-panel {
  color: var(--color-text-primary);
  white-space: pre-wrap;
}
.detail-qa__cursor {
  animation: detail-qa-cursor-blink 1s step-end infinite;
}
@keyframes detail-qa-cursor-blink { 50% { opacity: 0; } }
</style>`)
    expect(answerPanelStyleBlockHasNoAnimation(styles)).toBe(true)
  })

  it('demoMotionDoesNotObstructReading accepts static answer panel + labelFill graph', () => {
    const detailStyles = extractStyleBlocks(`
<style scoped>
.detail-qa__answer-panel {
  white-space: pre-wrap;
  color: var(--color-text-primary);
}
.detail-qa__cursor {
  animation: detail-qa-cursor-blink var(--duration-blink) step-end infinite;
}
</style>`)
    const graphUtil = 'labelFill: theme.labelFill, hover: { stroke: theme.hoverStroke }'
    const detailView = '<div class="detail-qa__answer-panel text-body-lg"><span class="detail-qa__answer-text">'

    expect(demoMotionDoesNotObstructReading(detailStyles, graphUtil, detailView)).toBe(true)
  })
})
