import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'

export type EmptyStateVariant = 'no-papers' | 'no-graph' | 'no-report'

export interface EmptyStatePreset {
  title: string
  description: string
}

export const EMPTY_STATE_PRESETS: Record<EmptyStateVariant, EmptyStatePreset> = {
  'no-papers': {
    title: PAPERS_BASELINE_COPY.emptyTitle,
    description: PAPERS_BASELINE_COPY.emptyBody,
  },
  'no-graph': {
    title: '暂无图谱',
    description: '论文 ready 后将展示逻辑图谱预览',
  },
  'no-report': {
    title: '还没有巡检报告',
    description: '选择两篇 ready 论文并运行巡检',
  },
}
