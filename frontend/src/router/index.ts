import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/papers',
      name: 'papers',
      component: () => import('@/views/PapersView.vue'),
    },
    {
      path: '/papers/:paperId',
      name: 'paper-detail',
      component: () => import('@/views/PaperDetailView.vue'),
      props: true,
    },
    {
      path: '/papers/:paperId/graph',
      name: 'paper-graph',
      component: () => import('@/views/PaperGraphView.vue'),
      props: true,
    },
    {
      path: '/patrol',
      name: 'patrol',
      component: () => import('@/views/PatrolView.vue'),
    },
  ],
})

export default router
