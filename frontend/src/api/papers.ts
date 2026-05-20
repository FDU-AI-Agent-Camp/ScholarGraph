import { http } from './client'
import type {
  DataResponse,
  PaginatedPapers,
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
}) {
  const { data } = await http.get<DataResponse<PaginatedPapers>>('/papers', { params })
  return data
}

export async function getPaper(paperId: string) {
  const { data } = await http.get<DataResponse<PaperDetail>>(`/papers/${paperId}`)
  return data
}

export async function getPaperStatus(paperId: string) {
  const { data } = await http.get<DataResponse<PaperStatusData>>(`/papers/${paperId}/status`)
  return data
}

export async function getPaperGraph(paperId: string) {
  const { data } = await http.get<DataResponse<UnifiedPaperGraph>>(`/papers/${paperId}/graph`)
  return data
}

export async function uploadPaper(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<DataResponse<{ paper_id: string; status: string; message: string }>>(
    '/papers',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}
