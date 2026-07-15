import { beforeEach, describe, expect, it, vi } from 'vitest'

const confirm = vi.fn()
const success = vi.fn()
const error = vi.fn()
const deletePaper = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { success: (...args: unknown[]) => success(...args), error: (...args: unknown[]) => error(...args) },
  ElMessageBox: { confirm: (...args: unknown[]) => confirm(...args) },
}))

vi.mock('@/api/papers', () => ({
  deletePaper: (...args: unknown[]) => deletePaper(...args),
}))

vi.mock('@/api/client', () => ({
  isApiClientError: (err: unknown): err is { message: string } =>
    typeof err === 'object' && err !== null && 'message' in err,
}))

import { confirmAndDeletePaper, PAPER_DELETE_COPY } from '@/utils/paperDelete'

describe('confirmAndDeletePaper', () => {
  beforeEach(() => {
    confirm.mockReset()
    success.mockReset()
    error.mockReset()
    deletePaper.mockReset()
  })

  it('ready uses standard confirm and DELETE without force', async () => {
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await expect(confirmAndDeletePaper('p-ready', 'ready')).resolves.toBe(true)

    expect(confirm).toHaveBeenCalledWith(
      PAPER_DELETE_COPY.confirmMessage,
      PAPER_DELETE_COPY.confirmTitle,
      expect.objectContaining({ confirmButtonText: PAPER_DELETE_COPY.confirmOk }),
    )
    expect(deletePaper).toHaveBeenCalledWith('p-ready', { force: false })
    expect(success).toHaveBeenCalledWith(PAPER_DELETE_COPY.success)
  })

  it('processing uses force warn modal and DELETE ?force=true', async () => {
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await expect(confirmAndDeletePaper('p-busy', 'processing')).resolves.toBe(true)

    expect(confirm).toHaveBeenCalledWith(
      PAPER_DELETE_COPY.forceConfirmMessage,
      PAPER_DELETE_COPY.forceConfirmTitle,
      expect.objectContaining({
        confirmButtonText: PAPER_DELETE_COPY.forceConfirmOk,
        confirmButtonClass: 'el-button--danger',
      }),
    )
    expect(deletePaper).toHaveBeenCalledWith('p-busy', { force: true })
  })

  it('indexing also forces delete', async () => {
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await expect(confirmAndDeletePaper('p-idx', 'indexing')).resolves.toBe(true)
    expect(deletePaper).toHaveBeenCalledWith('p-idx', { force: true })
  })

  it('cancel returns false without calling API', async () => {
    confirm.mockRejectedValue('cancel')

    await expect(confirmAndDeletePaper('p-ready', 'failed')).resolves.toBe(false)
    expect(deletePaper).not.toHaveBeenCalled()
  })
})
