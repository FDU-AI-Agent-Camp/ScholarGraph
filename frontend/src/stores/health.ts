/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as healthApi from '@/api/health'
import type { HealthData } from '@/api/types'
import { isPatrolDemoPath, pickPatrolService, shouldWarnRerankerOnPatrolDemo } from '@/utils/healthGuard'

const PATROL_ONBOARDING_SESSION_KEY = 'scholargraph.patrol-reranker-onboarding-dismissed'

export const useHealthStore = defineStore('health', () => {
  const health = ref<HealthData | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const loadError = ref<string | null>(null)
  const onboardingDismissed = ref(
    typeof sessionStorage !== 'undefined' && sessionStorage.getItem(PATROL_ONBOARDING_SESSION_KEY) === '1',
  )

  const patrolService = computed(() => pickPatrolService(health.value))

  async function ensureLoaded(force = false): Promise<void> {
    if (loaded.value && !force) {
      return
    }
    loading.value = true
    loadError.value = null
    try {
      const response = await healthApi.fetchHealth()
      health.value = response.data
      loaded.value = true
    } catch (error: unknown) {
      loadError.value = error instanceof Error ? error.message : 'health 请求失败'
    } finally {
      loading.value = false
    }
  }

  function shouldWarnOnRoute(routePath: string): boolean {
    return shouldWarnRerankerOnPatrolDemo(patrolService.value, routePath)
  }

  const showPatrolOnboardingModal = computed(() => {
    return shouldWarnOnRoute('/patrol') && !onboardingDismissed.value
  })

  function dismissPatrolOnboarding(): void {
    onboardingDismissed.value = true
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(PATROL_ONBOARDING_SESSION_KEY, '1')
    }
  }

  return {
    health,
    loading,
    loaded,
    loadError,
    patrolService,
    ensureLoaded,
    shouldWarnOnRoute,
    showPatrolOnboardingModal,
    dismissPatrolOnboarding,
  }
})

export function isPatrolRouteForPrefetch(path: string): boolean {
  return isPatrolDemoPath(path)
}
