import { http } from './client'
import type { DataResponse, PatrolReport } from './types'

export async function runPatrol(paperIds: string[]) {
  const { data } = await http.post<DataResponse<PatrolReport>>('/patrol', {
    paper_ids: paperIds,
  })
  return data
}
