import type { HealthData, PatrolServiceHealth, RerankerStatus } from '@/api/types'

export const DEMO_PATROL_ROUTE_PREFIX = '/patrol'

export function isPatrolDemoPath(path: string): boolean {
  return path === DEMO_PATROL_ROUTE_PREFIX || path.startsWith(`${DEMO_PATROL_ROUTE_PREFIX}/`)
}

export function isRerankerReady(status: RerankerStatus | undefined): boolean {
  return status === 'READY'
}

export function shouldWarnRerankerOnPatrolDemo(
  patrolService: PatrolServiceHealth | undefined,
  routePath: string,
): boolean {
  if (!isPatrolDemoPath(routePath)) {
    return false
  }
  if (!patrolService) {
    return false
  }
  if (patrolService.reranker_status === 'MOCK_LOCAL') {
    return false
  }
  return !isRerankerReady(patrolService.reranker_status)
}

export function pickPatrolService(health: HealthData | null): PatrolServiceHealth | undefined {
  return health?.components?.patrol_service
}
