/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** Format ISO timestamps for paper detail meta strip. */
export function formatDetailTime(iso: string | undefined): string {
  if (!iso) {
    return '—'
  }
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
