/** Shared delete confirm + API call for Papers list / Paper detail. */

import { ElMessage, ElMessageBox } from 'element-plus'

import { isApiClientError } from '@/api/client'
import * as papersApi from '@/api/papers'
import type { PaperStatus } from '@/api/types'
import { isActivePipelineStatus } from '@/utils/paperStatus'

export const PAPER_DELETE_COPY = {
  button: '删除',
  confirmTitle: '确认删除这篇论文？',
  confirmMessage: '将物理清空图谱、向量索引与原始 PDF，此操作不可恢复。',
  confirmOk: '确认删除',
  forceConfirmTitle: '强行中止并删除？',
  forceConfirmMessage:
    '警告：该文件正在处理中，强行删除将打断后台算力并物理清空所有相关图谱与索引。此操作不可恢复。',
  forceConfirmOk: '强行中止并删除',
  cancel: '取消',
  success: '论文已删除',
  failed: '删除失败',
} as const

export async function confirmAndDeletePaper(paperId: string, status: PaperStatus): Promise<boolean> {
  const force = isActivePipelineStatus(status)
  try {
    await ElMessageBox.confirm(
      force ? PAPER_DELETE_COPY.forceConfirmMessage : PAPER_DELETE_COPY.confirmMessage,
      force ? PAPER_DELETE_COPY.forceConfirmTitle : PAPER_DELETE_COPY.confirmTitle,
      {
        type: 'warning',
        confirmButtonText: force ? PAPER_DELETE_COPY.forceConfirmOk : PAPER_DELETE_COPY.confirmOk,
        cancelButtonText: PAPER_DELETE_COPY.cancel,
        confirmButtonClass: force ? 'el-button--danger' : undefined,
      },
    )
  } catch {
    return false
  }

  try {
    await papersApi.deletePaper(paperId, { force })
    ElMessage.success(PAPER_DELETE_COPY.success)
    return true
  } catch (error) {
    ElMessage.error(isApiClientError(error) ? error.message : PAPER_DELETE_COPY.failed)
    return false
  }
}
