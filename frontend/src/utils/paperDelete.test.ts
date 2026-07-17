/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { isVNode, type VNode } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'

const confirm = vi.fn()
const alert = vi.fn()
const success = vi.fn()
const error = vi.fn()
const deletePaper = vi.fn()
const getPaperStatus = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { success: (...args: unknown[]) => success(...args), error: (...args: unknown[]) => error(...args) },
  ElMessageBox: {
    confirm: (...args: unknown[]) => confirm(...args),
    alert: (...args: unknown[]) => alert(...args),
  },
}))

vi.mock('@/api/papers', () => ({
  deletePaper: (...args: unknown[]) => deletePaper(...args),
  getPaperStatus: (...args: unknown[]) => getPaperStatus(...args),
}))

import { confirmAndDeletePaper, PAPER_DELETE_COPY } from '@/utils/paperDelete'

function vnodePlainText(node: unknown): string {
  if (node == null) {
    return ''
  }
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

function expectForceConfirmCall(call: unknown[]): void {
  const [message, title, options] = call as [VNode, string, Record<string, unknown>]
  expect(isVNode(message)).toBe(true)
  const text = vnodePlainText(message)
  expect(text).toContain(PAPER_DELETE_COPY.forceConfirmLead)
  expect(text).toContain(PAPER_DELETE_COPY.forceConfirmBody)
  expect(title).toBe(PAPER_DELETE_COPY.forceConfirmTitle)
  expect(options).toEqual(
    expect.objectContaining({
      confirmButtonText: PAPER_DELETE_COPY.forceConfirmOk,
      confirmButtonClass: 'el-button--danger',
    }),
  )
  expect(options.dangerouslyUseHTMLString).toBeUndefined()
}

describe('confirmAndDeletePaper', () => {
  beforeEach(() => {
    confirm.mockReset()
    alert.mockReset()
    success.mockReset()
    error.mockReset()
    deletePaper.mockReset()
    getPaperStatus.mockReset()
  })

  it('preflights status then uses standard confirm for ready', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await expect(confirmAndDeletePaper('p-ready')).resolves.toBe(true)

    expect(getPaperStatus).toHaveBeenCalledWith('p-ready')
    expect(confirm).toHaveBeenCalledWith(
      PAPER_DELETE_COPY.confirmMessage,
      PAPER_DELETE_COPY.confirmTitle,
      expect.objectContaining({ confirmButtonText: PAPER_DELETE_COPY.confirmOk }),
    )
    expect(deletePaper).toHaveBeenCalledWith('p-ready', { force: false })
    expect(success).toHaveBeenCalledWith(PAPER_DELETE_COPY.success)
  })

  it('uses live processing status for force warn even when caller had stale ready', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'processing' } })
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await expect(confirmAndDeletePaper('p-busy')).resolves.toBe(true)

    expectForceConfirmCall(confirm.mock.calls[0] as unknown[])
    expect(deletePaper).toHaveBeenCalledWith('p-busy', { force: true })
  })

  it('indexing from preflight also forces delete with same active-pipeline copy', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'indexing' } })
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await expect(confirmAndDeletePaper('p-idx')).resolves.toBe(true)
    expectForceConfirmCall(confirm.mock.calls[0] as unknown[])
    expect(deletePaper).toHaveBeenCalledWith('p-idx', { force: true })
  })

  it('cancel returns false without calling DELETE', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'failed' } })
    confirm.mockRejectedValue('cancel')

    await expect(confirmAndDeletePaper('p-ready')).resolves.toBe(false)
    expect(deletePaper).not.toHaveBeenCalled()
  })

  it('preflight failure surfaces error and skips confirm', async () => {
    getPaperStatus.mockRejectedValue(new ApiClientError({ code: 'NETWORK_ERROR', message: 'offline' }, 0))

    await expect(confirmAndDeletePaper('p-offline')).resolves.toBe(false)

    expect(confirm).not.toHaveBeenCalled()
    expect(deletePaper).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledWith('offline')
  })

  it('retries with force=true after 409 when preflight showed terminal status (list race)', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValue(undefined)
    deletePaper
      .mockRejectedValueOnce(new ApiClientError({ code: 'PAPER_ALREADY_PROCESSING', message: 'busy' }, 409))
      .mockResolvedValueOnce(undefined)

    await expect(confirmAndDeletePaper('p-race')).resolves.toBe(true)

    expect(confirm).toHaveBeenCalledTimes(2)
    expect(confirm).toHaveBeenNthCalledWith(
      1,
      PAPER_DELETE_COPY.confirmMessage,
      PAPER_DELETE_COPY.confirmTitle,
      expect.any(Object),
    )
    expectForceConfirmCall(confirm.mock.calls[1] as unknown[])
    expect(deletePaper).toHaveBeenNthCalledWith(1, 'p-race', { force: false })
    expect(deletePaper).toHaveBeenNthCalledWith(2, 'p-race', { force: true })
    expect(success).toHaveBeenCalledWith(PAPER_DELETE_COPY.success)
  })

  it('409 force retry cancel returns false without second DELETE', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValueOnce(undefined).mockRejectedValueOnce('cancel')
    deletePaper.mockRejectedValueOnce(new ApiClientError({ code: 'PAPER_ALREADY_PROCESSING', message: 'busy' }, 409))

    await expect(confirmAndDeletePaper('p-race')).resolves.toBe(false)

    expect(deletePaper).toHaveBeenCalledTimes(1)
    expect(deletePaper).toHaveBeenCalledWith('p-race', { force: false })
  })

  it('maps VECTOR_STORE_UNAVAILABLE to productized safety alert (not raw error code toast)', async () => {
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValue(undefined)
    alert.mockResolvedValue(undefined)
    deletePaper.mockRejectedValue(
      new ApiClientError({ code: 'VECTOR_STORE_UNAVAILABLE', message: 'VECTOR_STORE_UNAVAILABLE' }, 503),
    )

    await expect(confirmAndDeletePaper('p-vector-down')).resolves.toBe(false)

    expect(alert).toHaveBeenCalledWith(
      PAPER_DELETE_COPY.vectorStoreUnavailable,
      PAPER_DELETE_COPY.vectorStoreUnavailableTitle,
      expect.objectContaining({ type: 'warning' }),
    )
    expect(PAPER_DELETE_COPY.vectorStoreUnavailableTitle).toBe('系统保护提示')
    expect(PAPER_DELETE_COPY.vectorStoreUnavailable).toContain('数据完整性')
    expect(PAPER_DELETE_COPY.vectorStoreUnavailable).not.toMatch(/Chroma|系统泄露/i)
    expect(error).not.toHaveBeenCalled()
  })

  it('fires onDeleteInFlight only around DELETE attempts', async () => {
    const inFlight: boolean[] = []
    getPaperStatus.mockResolvedValue({ data: { status: 'ready' } })
    confirm.mockResolvedValue(undefined)
    deletePaper.mockResolvedValue(undefined)

    await confirmAndDeletePaper('p-hook', {
      onDeleteInFlight: (active) => inFlight.push(active),
    })

    expect(inFlight).toEqual([true, false])
  })
})
