import { postData } from './client'
import type { DataResponse, PatrolReport } from './types'

export async function runPatrol(paperIds: string[]): Promise<DataResponse<PatrolReport>> {
  return postData<PatrolReport>('/patrol', { paper_ids: paperIds })
}
