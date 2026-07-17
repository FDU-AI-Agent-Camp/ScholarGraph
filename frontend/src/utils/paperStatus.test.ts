/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import type { PaperStatus, PaperStatusData } from '@/api/types'
import failedStatusEnvelope from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import { failedStatus, processingStatus, readyStatus } from '@/test/fixtures/paperStatus'
import {
  isActivePipelineStatus,
  isFailedStatus,
  isGraphInteractiveStatus,
  isListActivePollStatus,
  listHasActivePollStatus,
  isPreviewAvailableStatus,
  isQaReadyStatus,
  isReadyStatus,
  isTerminalStatus,
} from '@/utils/paperStatus'

describe('paperStatus helpers', () => {
  it('isTerminalStatus stops polling for ready / ready_with_warnings / failed', () => {
    expect(isTerminalStatus('ready')).toBe(true)
    expect(isTerminalStatus('ready_with_warnings')).toBe(true)
    expect(isTerminalStatus('failed')).toBe(true)
    expect(isTerminalStatus('pending')).toBe(false)
    expect(isTerminalStatus('processing')).toBe(false)
    expect(isTerminalStatus('indexing')).toBe(false)
  })

  it('isActivePipelineStatus covers processing and indexing only', () => {
    expect(isActivePipelineStatus('processing')).toBe(true)
    expect(isActivePipelineStatus('indexing')).toBe(true)
    expect(isActivePipelineStatus('pending')).toBe(false)
    expect(isActivePipelineStatus('ready')).toBe(false)
    expect(isActivePipelineStatus('failed')).toBe(false)
  })

  it('isListActivePollStatus covers pending, processing, and indexing', () => {
    expect(isListActivePollStatus('pending')).toBe(true)
    expect(isListActivePollStatus('processing')).toBe(true)
    expect(isListActivePollStatus('indexing')).toBe(true)
    expect(isListActivePollStatus('ready')).toBe(false)
    expect(listHasActivePollStatus([{ status: 'ready' }, { status: 'failed' }])).toBe(false)
    expect(listHasActivePollStatus([{ status: 'ready' }, { status: 'processing' }])).toBe(true)
  })

  it('isFailedStatus narrows failed payloads with error fields', () => {
    expect(isFailedStatus(processingStatus)).toBe(false)
    expect(isFailedStatus(readyStatus)).toBe(false)
    expect(isFailedStatus(failedStatus)).toBe(true)
    if (isFailedStatus(failedStatus)) {
      expect(failedStatus.error_code).toBe('LLM_JSON_INVALID')
      expect(failedStatus.failed_during).toBe('classifying')
    }
  })

  it('isReadyStatus narrows ready payloads', () => {
    expect(isReadyStatus(readyStatus)).toBe(true)
    expect(isReadyStatus(failedStatus)).toBe(false)
  })

  it('isReadyStatus stays narrow — RWW is not strict ready (G1)', () => {
    const rww: PaperStatusData = {
      ...readyStatus,
      status: 'ready_with_warnings',
      message: '图谱可用，质量门控未完全通过',
    }
    expect(isReadyStatus(rww)).toBe(false)
    expect(isReadyStatus(readyStatus)).toBe(true)
  })

  it('isFailedStatus works on canonical docs/api failed fixture', () => {
    const fixture = failedStatusEnvelope.data as PaperStatusData
    expect(isFailedStatus(fixture)).toBe(true)
    if (isFailedStatus(fixture)) {
      expect(fixture.error_code).toBe('LLM_JSON_INVALID')
    }
  })

  describe('G1 capability predicates', () => {
    const matrix: Array<{
      status: PaperStatus
      graph: boolean
      qa: boolean
      previewWhenFlag: boolean
    }> = [
      { status: 'ready', graph: true, qa: true, previewWhenFlag: false },
      { status: 'ready_with_warnings', graph: true, qa: true, previewWhenFlag: false },
      { status: 'processing', graph: false, qa: false, previewWhenFlag: true },
      { status: 'indexing', graph: false, qa: false, previewWhenFlag: true },
      { status: 'pending', graph: false, qa: false, previewWhenFlag: true },
      { status: 'failed', graph: false, qa: false, previewWhenFlag: true },
    ]

    it('isGraphInteractiveStatus unlocks ready ∪ ready_with_warnings only', () => {
      for (const row of matrix) {
        expect(isGraphInteractiveStatus(row.status), row.status).toBe(row.graph)
      }
    })

    it('isQaReadyStatus mirrors graph interactive readiness', () => {
      for (const row of matrix) {
        expect(isQaReadyStatus(row.status), row.status).toBe(row.qa)
      }
    })

    it('isPreviewAvailableStatus only when not fully interactive and preview flag set', () => {
      for (const row of matrix) {
        expect(isPreviewAvailableStatus(row.status, true), `${row.status}+preview`).toBe(row.previewWhenFlag)
        expect(isPreviewAvailableStatus(row.status, false), `${row.status}+no-preview`).toBe(false)
      }
    })

    it('RWW never falls into thin preview even when preview_available is true', () => {
      expect(isPreviewAvailableStatus('ready_with_warnings', true)).toBe(false)
      expect(isGraphInteractiveStatus('ready_with_warnings')).toBe(true)
    })
  })
})
