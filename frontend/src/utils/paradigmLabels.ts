/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import type { Paradigm } from '@/api/types'

/** User-facing Chinese labels for API paradigm codes (HSS / STEM). */
export const PARADIGM_LABELS: Record<Paradigm, string> = {
  HSS: '人文社科',
  STEM: '理工科',
}

/**
 * Map API paradigm code to localized display label.
 * Unknown or missing values return 「未知」.
 */
export function getParadigmLabel(paradigm: Paradigm | null | string | undefined): string {
  if (paradigm === 'HSS' || paradigm === 'STEM') {
    return PARADIGM_LABELS[paradigm]
  }
  return '未知'
}
