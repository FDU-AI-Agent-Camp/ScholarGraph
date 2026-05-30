import { postData } from './client'
import type { DataResponse, PatrolMode, PatrolReport } from './types'

export interface RunPatrolOptions {
  mode?: PatrolMode
}

export async function runPatrol(
  paperIds: string[],
  options: RunPatrolOptions = {},
): Promise<DataResponse<PatrolReport>> {
  const mode = options.mode ?? 'lens_clash'
  return postData<PatrolReport>('/patrol', { paper_ids: paperIds, mode })
}
