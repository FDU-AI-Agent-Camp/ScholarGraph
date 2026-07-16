/** Shared delete confirm + API call for Papers list / Paper detail. */

import { ElMessage, ElMessageBox } from 'element-plus'
import { h, type VNode } from 'vue'

import { isApiClientError } from '@/api/client'
import * as papersApi from '@/api/papers'
import type { PaperStatus } from '@/api/types'
import { isActivePipelineStatus } from '@/utils/paperStatus'

export const PAPER_DELETE_COPY = {
  button: '删除',
  confirmTitle: '确认删除这篇论文？',
  confirmMessage: '将物理清空图谱、向量索引与原始 PDF，此操作不可恢复。',
  confirmOk: '确认删除',
  forceConfirmTitle: '强制删除确认',
  forceConfirmLead: '该论文当前正在提取内容或构建语义索引。',
  forceConfirmBody: '强行删除将中断后台计算，并物理清空所有已生成的图谱和问答数据。此操作不可恢复，是否确认删除？',
  forceConfirmOk: '强行中止并删除',
  cancel: '取消',
  success: '论文已删除',
  failed: '删除失败',
  vectorStoreUnavailableTitle: '系统保护提示',
  vectorStoreUnavailable:
    '底层数据库服务正在维护或暂时不可用。为保证您的数据完整性，系统已安全暂停本次物理清理。请稍后再试。',
} as const

export type DeletePaperHooks = {
  /** Fires only around ``DELETE`` network attempts (not confirm modals). */
  onDeleteInFlight?: (inFlight: boolean) => void
}

/**
 * Force-delete body as a VNode so ElMessageBox never needs ``dangerouslyUseHTMLString``.
 * Plain-text children stay XSS-safe even if a future caller interpolates dynamic strings.
 */
export function buildForceDeleteConfirmMessage(): VNode {
  return h('div', { class: 'paper-delete-force-confirm' }, [
    h('p', { class: 'paper-delete-force-confirm__lead' }, PAPER_DELETE_COPY.forceConfirmLead),
    h('p', { class: 'paper-delete-force-confirm__body' }, PAPER_DELETE_COPY.forceConfirmBody),
  ])
}

async function confirmDeleteDialog(force: boolean): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      force ? buildForceDeleteConfirmMessage() : PAPER_DELETE_COPY.confirmMessage,
      force ? PAPER_DELETE_COPY.forceConfirmTitle : PAPER_DELETE_COPY.confirmTitle,
      {
        type: 'warning',
        confirmButtonText: force ? PAPER_DELETE_COPY.forceConfirmOk : PAPER_DELETE_COPY.confirmOk,
        cancelButtonText: PAPER_DELETE_COPY.cancel,
        confirmButtonClass: force ? 'el-button--danger' : undefined,
      },
    )
    return true
  } catch {
    return false
  }
}

async function fetchLivePaperStatus(paperId: string): Promise<PaperStatus> {
  const result = await papersApi.getPaperStatus(paperId)
  return result.data.status
}

function isProcessingConflict(error: unknown): boolean {
  return isApiClientError(error) && error.code === 'PAPER_ALREADY_PROCESSING'
}

function isVectorStoreUnavailable(error: unknown): boolean {
  return isApiClientError(error) && error.code === 'VECTOR_STORE_UNAVAILABLE'
}

function resolveDeleteErrorMessage(error: unknown): string {
  if (isApiClientError(error)) {
    return error.message
  }
  return PAPER_DELETE_COPY.failed
}

async function notifyDeleteFailure(error: unknown): Promise<void> {
  if (isVectorStoreUnavailable(error)) {
    await ElMessageBox.alert(PAPER_DELETE_COPY.vectorStoreUnavailable, PAPER_DELETE_COPY.vectorStoreUnavailableTitle, {
      type: 'warning',
    }).catch(() => undefined)
    return
  }
  ElMessage.error(resolveDeleteErrorMessage(error))
}

async function deletePaperWithHook(paperId: string, force: boolean, hooks?: DeletePaperHooks): Promise<void> {
  hooks?.onDeleteInFlight?.(true)
  try {
    await papersApi.deletePaper(paperId, { force })
  } finally {
    hooks?.onDeleteInFlight?.(false)
  }
}

/** Stage 2: 409 escape — force confirm then ``DELETE ?force=true`` (symmetric with reextract). */
async function retryDeleteAfterProcessingConflict(paperId: string, hooks?: DeletePaperHooks): Promise<boolean> {
  if (!(await confirmDeleteDialog(true))) {
    return false
  }
  try {
    await deletePaperWithHook(paperId, true, hooks)
    ElMessage.success(PAPER_DELETE_COPY.success)
    return true
  } catch (retryError) {
    await notifyDeleteFailure(retryError)
    return false
  }
}

/**
 * Delete flow shared by detail + list (single entry, identical behavior).
 *
 * 1. Pre-flight: ``GET /papers/{id}/status`` — kill stale list/detail snapshots.
 * 2. Confirm modal (standard vs force) from live status via ``isActivePipelineStatus``.
 * 3. Stage-1 ``DELETE`` with computed ``force``.
 * 4. On ``409 PAPER_ALREADY_PROCESSING`` when stage-1 used ``force=false``:
 *    stage-2 force confirm → ``DELETE ?force=true``.
 */
export async function confirmAndDeletePaper(paperId: string, hooks?: DeletePaperHooks): Promise<boolean> {
  let liveStatus: PaperStatus
  try {
    liveStatus = await fetchLivePaperStatus(paperId)
  } catch (error) {
    await notifyDeleteFailure(error)
    return false
  }

  const force = isActivePipelineStatus(liveStatus)
  if (!(await confirmDeleteDialog(force))) {
    return false
  }

  try {
    await deletePaperWithHook(paperId, force, hooks)
    ElMessage.success(PAPER_DELETE_COPY.success)
    return true
  } catch (error) {
    if (!force && isProcessingConflict(error)) {
      return retryDeleteAfterProcessingConflict(paperId, hooks)
    }
    await notifyDeleteFailure(error)
    return false
  }
}
