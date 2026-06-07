import type { FailedDuringStage, PaperStatus, PipelineStage } from '@/api/types'

import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'

export interface PipelineStepDefinition {
  stage: PipelineStage
  label: string
}

export const PIPELINE_STEPS: PipelineStepDefinition[] = [
  { stage: 'ingesting', label: '正在解析 PDF' },
  { stage: 'head_refining', label: '精炼文档头部' },
  { stage: 'classifying', label: '范式分类' },
  { stage: 'extracting', label: '抽取图谱' },
  { stage: 'storing', label: '写入存储' },
  { stage: 'ready', label: '建图完成' },
]

export const PIPELINE_REFRESH_CAPTION = DETAIL_BASELINE_COPY.refreshCaption

export type PipelineStepVisualState = 'pending' | 'active' | 'done' | 'failed'

const WORKFLOW_STAGES: PipelineStage[] = [
  'ingesting',
  'head_refining',
  'classifying',
  'extracting',
  'storing',
  'ready',
]

function stageIndex(stage: PipelineStage | null | undefined): number {
  if (!stage) {
    return -1
  }
  return WORKFLOW_STAGES.indexOf(stage)
}

/** Map API stage + status into vertical stepper visual states (design-spec §9.7.2). */
export function resolvePipelineStepStates(
  currentStage: PipelineStage | null | undefined,
  paperStatus: PaperStatus,
  failedDuring?: FailedDuringStage | null,
): PipelineStepVisualState[] {
  if (paperStatus === 'ready') {
    return PIPELINE_STEPS.map(() => 'done')
  }

  const activeIndex = stageIndex(currentStage === 'failed' ? (failedDuring ?? currentStage) : currentStage)
  const failedIndex = paperStatus === 'failed' ? stageIndex(failedDuring ?? currentStage) : -1

  return PIPELINE_STEPS.map((_step, index) => {
    if (failedIndex >= 0 && index === failedIndex) {
      return 'failed'
    }
    if (failedIndex >= 0 && index < failedIndex) {
      return 'done'
    }
    if (activeIndex >= 0 && index < activeIndex) {
      return 'done'
    }
    if (activeIndex >= 0 && index === activeIndex && paperStatus !== 'failed') {
      return 'active'
    }
    if (paperStatus === 'pending' && index === 0) {
      return 'pending'
    }
    return 'pending'
  })
}
