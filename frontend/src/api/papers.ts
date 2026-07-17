/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { deleteData, getData, postData } from './client'
import type {
  DataResponse,
  PaginatedPapers,
  PaperCreateResult,
  PaperDetail,
  PaperStatus,
  PaperStatusData,
  Paradigm,
  UnifiedPaperGraph,
} from './types'

export async function listPapers(params?: {
  paradigm?: Paradigm
  status?: PaperStatus
  offset?: number
  limit?: number
}): Promise<DataResponse<PaginatedPapers>> {
  return getData<PaginatedPapers>('/papers', { params })
}

export async function getPaper(paperId: string): Promise<DataResponse<PaperDetail>> {
  return getData<PaperDetail>(`/papers/${paperId}`)
}

export async function getPaperStatus(paperId: string): Promise<DataResponse<PaperStatusData>> {
  return getData<PaperStatusData>(`/papers/${paperId}/status`)
}

export async function getPaperGraph(paperId: string): Promise<DataResponse<UnifiedPaperGraph>> {
  return getData<UnifiedPaperGraph>(`/papers/${paperId}/graph`)
}

export async function forceReextractPaper(
  paperId: string,
  options?: { force?: boolean },
): Promise<DataResponse<PaperStatusData>> {
  return postData<PaperStatusData>(`/papers/${paperId}/reextract`, undefined, {
    params: { force: options?.force === true ? true : undefined },
    suppressErrorToast: true,
  })
}

export async function deletePaper(paperId: string, options?: { force?: boolean }): Promise<void> {
  await deleteData(`/papers/${paperId}`, {
    params: { force: options?.force === true ? true : undefined },
    suppressErrorToast: true,
  })
}

export async function uploadPaper(file: File): Promise<DataResponse<PaperCreateResult>> {
  const form = new FormData()
  form.append('file', file)
  return postData<PaperCreateResult>('/papers', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    suppressErrorToast: true,
  })
}
