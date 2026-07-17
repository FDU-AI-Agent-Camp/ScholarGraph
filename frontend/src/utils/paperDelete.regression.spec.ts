/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Delete self-heal regression gate — pre-flight status + 409 force escape.
 *
 * Guards against stale store snapshots and missing 409 retry (symmetric with reextract).
 */
import { isVNode, type VNode } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import { PAPER_DELETE_COPY, confirmAndDeletePaper } from '@/utils/paperDelete'

const confirm = vi.fn()
const success = vi.fn()
const error = vi.fn()
const deletePaper = vi.fn()
const getPaperStatus = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { success: (...args: unknown[]) => success(...args), error: (...args: unknown[]) => error(...args) },
  ElMessageBox: {
    confirm: (...args: unknown[]) => confirm(...args),
    alert: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/papers', () => ({
  deletePaper: (...args: unknown[]) => deletePaper(...args),
  getPaperStatus: (...args: unknown[]) => getPaperStatus(...args),
}))

function vnodePlainText(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (!isVNode(node)) {
    return ''
  }
  const children = node.children
  if (typeof children === 'string') {
    return children
  }
  if (Array.isArray(children)) {
    return children.map((child) => vnodePlainText(child)).join('')
  }
  return ''
}

describe('paperDelete regression gate', () => {
  beforeEach(() => {
    confirm.mockReset()
    success.mockReset()
    error.mockReset()
    deletePaper.mockReset()
    getPaperStatus.mockReset()
  })

  it('409 cascade: no error toast on first conflict; upgrades to force confirm then DELETE ?force=true', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValue(undefined)
    deletePaper
      .mockRejectedValueOnce(new ApiClientError({ code: 'PAPER_ALREADY_PROCESSING', message: 'busy' }, 409))
      .mockResolvedValueOnce(undefined)

    await expect(confirmAndDeletePaper('p-409-escape')).resolves.toBe(true)

    expect(deletePaper).toHaveBeenNthCalledWith(1, 'p-409-escape', { force: false })
    expect(error).not.toHaveBeenCalled()
    expect(confirm).toHaveBeenCalledTimes(2)
    const [message, title, options] = confirm.mock.calls[1] as [VNode, string, Record<string, unknown>]
    expect(isVNode(message)).toBe(true)
    expect(vnodePlainText(message)).toContain(PAPER_DELETE_COPY.forceConfirmLead)
    expect(title).toBe(PAPER_DELETE_COPY.forceConfirmTitle)
    expect(options).toEqual(
      expect.objectContaining({
        confirmButtonText: PAPER_DELETE_COPY.forceConfirmOk,
        confirmButtonClass: 'el-button--danger',
      }),
    )
    expect(options.dangerouslyUseHTMLString).toBeUndefined()
    expect(deletePaper).toHaveBeenNthCalledWith(2, 'p-409-escape', { force: true })
    expect(success).toHaveBeenCalledWith(PAPER_DELETE_COPY.success)
  })

  it('409 cascade cancel: still no error toast when user declines force upgrade', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValueOnce(undefined).mockRejectedValueOnce('cancel')
    deletePaper.mockRejectedValueOnce(new ApiClientError({ code: 'PAPER_ALREADY_PROCESSING', message: 'busy' }, 409))

    await expect(confirmAndDeletePaper('p-409-cancel')).resolves.toBe(false)

    expect(error).not.toHaveBeenCalled()
    expect(deletePaper).toHaveBeenCalledTimes(1)
  })
})
