/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { RouteName } from './meta'

import './meta'

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: RouteName.Home,
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '工作台', nav: true },
  },
  {
    path: '/papers',
    name: RouteName.Papers,
    component: () => import('@/views/PapersView.vue'),
    meta: { title: '文献库', nav: true },
  },
  {
    path: '/papers/:paperId',
    name: RouteName.PaperDetail,
    component: () => import('@/views/PaperDetailView.vue'),
    props: (route) => ({
      paperId: typeof route.params.paperId === 'string' ? route.params.paperId : '',
    }),
    meta: { title: '论文详情' },
  },
  {
    path: '/papers/:paperId/graph',
    name: RouteName.PaperGraph,
    component: () => import('@/views/PaperGraphView.vue'),
    props: (route) => ({
      paperId: typeof route.params.paperId === 'string' ? route.params.paperId : '',
    }),
    meta: { title: '知识图谱', fullBleed: true },
  },
  {
    path: '/patrol',
    name: RouteName.Patrol,
    component: () => import('@/views/PatrolView.vue'),
    meta: { title: '共同体巡检', nav: true },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach(async (to) => {
  const { isPatrolRouteForPrefetch, useHealthStore } = await import('@/stores/health')
  if (isPatrolRouteForPrefetch(to.path)) {
    const healthStore = useHealthStore()
    await healthStore.ensureLoaded()
  }
})

export default router
