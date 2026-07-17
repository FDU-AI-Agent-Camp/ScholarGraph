/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, expect, it } from 'vitest'

import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { PIPELINE_STEPS, PIPELINE_REFRESH_CAPTION, resolvePipelineStepStates } from '@/utils/pipelineSteps'

describe('resolvePipelineStepStates', () => {
  it('marks all steps done when status is ready', () => {
    expect(resolvePipelineStepStates('ready', 'ready')).toEqual(['done', 'done', 'done', 'done', 'done', 'done'])
  })

  it('marks all steps done when status is ready_with_warnings (G1)', () => {
    expect(resolvePipelineStepStates('ready', 'ready_with_warnings')).toEqual([
      'done',
      'done',
      'done',
      'done',
      'done',
      'done',
    ])
  })

  it('marks prior steps done and current active while processing', () => {
    expect(resolvePipelineStepStates('classifying', 'processing')).toEqual([
      'done',
      'done',
      'active',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('marks head_refining as active between ingest and classify', () => {
    expect(resolvePipelineStepStates('head_refining', 'processing')).toEqual([
      'done',
      'active',
      'pending',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('marks failed step when pipeline fails during a stage', () => {
    expect(resolvePipelineStepStates('failed', 'failed', 'classifying')).toEqual([
      'done',
      'done',
      'failed',
      'pending',
      'pending',
      'pending',
    ])
  })

  it('exposes baseline step labels in pipeline order', () => {
    expect(PIPELINE_STEPS.map((step) => step.label)).toEqual([
      '正在解析 PDF',
      '精炼文档头部',
      '范式分类',
      '抽取图谱',
      '写入存储',
      '建图完成',
    ])
    expect(PIPELINE_REFRESH_CAPTION).toBe(DETAIL_BASELINE_COPY.refreshCaption)
  })
})
