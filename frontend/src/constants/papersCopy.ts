/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/** design-spec §8 + ui-design-progress §1.4.4 Papers baseline copy. */
export const PAPERS_BASELINE_COPY = {
  title: '文献库',
  subtitle: '管理已上传论文，查看解构进度与图谱入口',
  uploadSection: '上传论文',
  tableSection: '全部文献',
  uploadMain: '拖拽 PDF 到此处，或',
  uploadClick: '点击上传',
  uploadTip: '建议 ≤32MB · 上传后自动进入解构流水线',
  uploadSuccess: '已提交解构，正在处理…',
  uploading: '上传中…',
  emptyTitle: '还没有论文',
  emptyBody: '上传 PDF 开始自动解构',
  emptyCta: '上传 PDF',
  uploadErrorFallback: '上传失败，请稍后重试',
  uploadRetryHint: '请检查 PDF 是否可读后重新上传',
  uploadRetryButton: '重新上传',
  nonPdfWarning: '请上传 PDF 文件',
} as const
