/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * G1 Layer 1 — exhaustive capability-predicate matrix (防退化卡点).
 * Future success terminals must be added to GRAPH_INTERACTIVE set + this matrix together.
 */
import { describe, expect, it } from 'vitest'

import type { PaperStatus } from '@/api/types'
import {
  isGraphInteractiveStatus,
  isPreviewAvailableStatus,
  isQaReadyStatus,
  isReadyStatus,
  isTerminalStatus,
} from '@/utils/paperStatus'
import { readyStatus, readyWithWarningsStatus } from '@/test/fixtures/paperStatus'

type MatrixRow = {
  name: string
  status: PaperStatus
  previewAvailable: boolean
  expectGraph: boolean
  expectPreview: boolean
  expectStrictReady: boolean
}

const CAPABILITY_MATRIX: MatrixRow[] = [
  {
    name: 'test_rww_is_interactive — ready',
    status: 'ready',
    previewAvailable: true,
    expectGraph: true,
    expectPreview: false,
    expectStrictReady: true,
  },
  {
    name: 'test_rww_is_interactive — ready_with_warnings',
    status: 'ready_with_warnings',
    previewAvailable: true,
    expectGraph: true,
    expectPreview: false,
    expectStrictReady: false,
  },
  {
    name: 'processing + preview_available → thin preview',
    status: 'processing',
    previewAvailable: true,
    expectGraph: false,
    expectPreview: true,
    expectStrictReady: false,
  },
  {
    name: 'indexing + preview_available → thin preview',
    status: 'indexing',
    previewAvailable: true,
    expectGraph: false,
    expectPreview: true,
    expectStrictReady: false,
  },
  {
    name: 'pending without preview → neither gate',
    status: 'pending',
    previewAvailable: false,
    expectGraph: false,
    expectPreview: false,
    expectStrictReady: false,
  },
  {
    name: 'failed → both predicates false (even with preview flag)',
    status: 'failed',
    previewAvailable: true,
    expectGraph: false,
    expectPreview: true,
    expectStrictReady: false,
  },
]

describe('G1 paperStatus capability matrix (unit)', () => {
  it.each(CAPABILITY_MATRIX)('$name', (row) => {
    expect(isGraphInteractiveStatus(row.status)).toBe(row.expectGraph)
    expect(isQaReadyStatus(row.status)).toBe(row.expectGraph)
    expect(isPreviewAvailableStatus(row.status, row.previewAvailable)).toBe(row.expectPreview)
    expect(isReadyStatus({ ...readyStatus, status: row.status })).toBe(row.expectStrictReady)
  })

  it('RWW payload is terminal but never strict-ready', () => {
    expect(isTerminalStatus(readyWithWarningsStatus.status)).toBe(true)
    expect(isReadyStatus(readyWithWarningsStatus)).toBe(false)
    expect(isGraphInteractiveStatus(readyWithWarningsStatus.status)).toBe(true)
    expect(isPreviewAvailableStatus(readyWithWarningsStatus.status, true)).toBe(false)
  })
})
