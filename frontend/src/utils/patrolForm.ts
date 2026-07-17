/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** Patrol form helpers (paper selection validation and API error presentation). */

import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

export const PATROL_PAPER_COUNT = 2

export type PatrolErrorCtaKind = 'papers' | 'reset-selection'

export interface PatrolErrorPresentation {
  title: string
  description?: string
  ctaLabel?: string
  ctaKind?: PatrolErrorCtaKind
}

export function parsePatrolPaperIds(text: string): string[] {
  return text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function buildPatrolPaperIds(paperA: string, paperB: string): [string, string] {
  return [paperA.trim(), paperB.trim()]
}

export function validatePatrolSelection(paperA: string, paperB: string): string | null {
  const [firstId, secondId] = buildPatrolPaperIds(paperA, paperB)
  if (!firstId || !secondId) {
    return PATROL_BASELINE_COPY.validationExactTwo
  }
  if (firstId === secondId) {
    return PATROL_BASELINE_COPY.validationDuplicate(firstId)
  }
  return null
}

export function validatePatrolPaperIds(paperIds: string[]): string | null {
  if (paperIds.length !== PATROL_PAPER_COUNT) {
    return PATROL_BASELINE_COPY.validationExactTwo
  }
  const [firstId, secondId] = paperIds
  if (!firstId || !secondId) {
    return PATROL_BASELINE_COPY.validationExactTwo
  }
  if (firstId === secondId) {
    return PATROL_BASELINE_COPY.validationDuplicate(firstId)
  }
  return null
}

export function resolvePatrolApiError(code: string | null, message: string): PatrolErrorPresentation {
  if (code === 'GRAPH_NOT_READY') {
    return {
      title: PATROL_BASELINE_COPY.graphNotReadyTitle,
      description: message || PATROL_BASELINE_COPY.graphNotReadyDescription,
      ctaLabel: PATROL_BASELINE_COPY.graphNotReadyCta,
      ctaKind: 'papers',
    }
  }
  if (code === 'PATROL_INSUFFICIENT_DATA') {
    return {
      title: PATROL_BASELINE_COPY.insufficientDataTitle,
      description: PATROL_BASELINE_COPY.insufficientDataDescription,
      ctaLabel: PATROL_BASELINE_COPY.insufficientDataCta,
      ctaKind: 'reset-selection',
    }
  }
  return { title: message }
}

/** Legacy string formatter kept for integration tests and logging. */
export function formatPatrolError(code: string | null, message: string): string {
  const presentation = resolvePatrolApiError(code, message)
  if (presentation.description) {
    return `${presentation.title}：${presentation.description}`
  }
  return presentation.title
}
