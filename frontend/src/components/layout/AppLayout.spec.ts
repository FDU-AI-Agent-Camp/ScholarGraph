/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AppLayout from '@/components/layout/AppLayout.vue'
import { SHELL_BASELINE_COPY } from '@/constants/shellCopy'
import { RouteName } from '@/router/meta'

const routeMeta = ref<{ title?: string; fullBleed?: boolean }>({ title: '文献库' })
const routePath = ref('/papers')
const routeName = ref<string | symbol | null | undefined>(RouteName.Papers)
const routeParams = ref<Record<string, string | string[]>>({})
const routerPush = vi.hoisted(() => vi.fn())

vi.mock('@/api/health', () => ({
  fetchHealth: vi.fn().mockResolvedValue({
    data: {
      status: 'healthy',
      version: '0.0.0-test',
      components: {
        patrol_service: {
          status: 'fully_functional',
          claim_rq_funnel_enabled: true,
          reranker_status: 'READY',
          active_profile: 'ci',
        },
      },
      llm_mode: 'mock',
      llm_connected: true,
      llm_note: 'ok',
    },
    meta: { request_id: 'test' },
  }),
}))

function mockMatchMedia(matches = false): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  })
}

vi.mock('vue-router', () => ({
  useRoute: () => ({
    get path() {
      return routePath.value
    },
    get meta() {
      return routeMeta.value
    },
    get name() {
      return routeName.value
    },
    get params() {
      return routeParams.value
    },
  }),
  useRouter: () => ({
    push: routerPush,
  }),
}))

function mountLayout(): VueWrapper {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(AppLayout, {
    global: {
      plugins: [pinia],
      stubs: {
        transition: false,
        PatrolRerankerOnboardingGuard: true,
        'el-container': { template: '<div class="el-container-stub"><slot /></div>' },
        'el-aside': {
          props: ['width'],
          template: '<aside class="el-aside-stub" :data-width="width"><slot /></aside>',
        },
        'el-header': { template: '<header class="el-header-stub"><slot /></header>' },
        'el-main': { template: '<main class="el-main-stub" :class="$attrs.class"><slot /></main>' },
        'el-menu': {
          props: ['defaultActive'],
          emits: ['select'],
          template:
            '<nav class="el-menu-stub" :data-active="defaultActive" @click="$emit(\'select\', \'/patrol\')"><slot /></nav>',
        },
        'el-menu-item': { template: '<div class="el-menu-item-stub"><slot /></div>' },
        'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
        'el-link': {
          props: ['href', 'target', 'type'],
          template: '<a class="el-link-stub" :href="href" :target="target"><slot /></a>',
        },
        'el-breadcrumb': { template: '<nav class="el-breadcrumb-stub"><slot /></nav>' },
        'el-breadcrumb-item': {
          props: ['to'],
          template: '<span class="el-breadcrumb-item-stub" :data-to="to"><slot /></span>',
        },
        'router-link': { props: ['to'], template: '<a class="router-link-stub" :href="to"><slot /></a>' },
        'router-view': {
          setup() {
            const mockRoute = { fullPath: '/papers' }
            const mockComponent = { template: '<div class="route-view-content" />' }
            return { mockRoute, mockComponent }
          },
          template: '<div class="router-view-stub"><slot :Component="mockComponent" :route="mockRoute" /></div>',
        },
        HomeFilled: { template: '<svg data-testid="icon-home" />' },
        Document: { template: '<svg data-testid="icon-document" />' },
        Search: { template: '<svg data-testid="icon-search" />' },
        Menu: { template: '<svg data-testid="icon-menu" />' },
        Close: { template: '<svg data-testid="icon-close" />' },
      },
    },
  })
}

describe('AppLayout', () => {
  beforeEach(() => {
    mockMatchMedia(false)
    routeMeta.value = { title: '文献库' }
    routePath.value = '/papers'
    routeName.value = RouteName.Papers
    routeParams.value = {}
    routerPush.mockClear()
  })

  it('shows route meta title in header', () => {
    const wrapper = mountLayout()

    expect(wrapper.find('.header-title').text()).toBe('文献库')
    expect(wrapper.text()).not.toContain('学术论文逻辑解构')
  })

  it('falls back when meta title is missing', () => {
    routeMeta.value = {}
    const wrapper = mountLayout()

    expect(wrapper.find('.header-title').text()).toBe('ScholarGraph')
  })

  it('shows API docs link in header', () => {
    const wrapper = mountLayout()
    const link = wrapper.find('.header-api-link')

    expect(link.text()).toContain('API 文档 ↗')
    expect(link.attributes('href')).toBe('http://127.0.0.1:8000/docs')
    expect(link.attributes('target')).toBe('_blank')
  })

  it('wraps content in page-card when not fullBleed', () => {
    const wrapper = mountLayout()

    expect(wrapper.find('.page-card').exists()).toBe(true)
    expect(wrapper.find('.shell-content--full-bleed').exists()).toBe(false)
    expect(wrapper.find('.el-main-stub').classes()).not.toContain('main--full-bleed')
  })

  it('uses full-bleed shell on graph routes', () => {
    routeMeta.value = { title: '知识图谱', fullBleed: true }
    routePath.value = '/papers/hss-001/graph'
    routeName.value = RouteName.PaperGraph
    routeParams.value = { paperId: 'hss-001' }
    const wrapper = mountLayout()

    expect(wrapper.find('.page-card').exists()).toBe(false)
    expect(wrapper.find('.shell-content--full-bleed').exists()).toBe(true)
    expect(wrapper.find('.el-main-stub').classes()).toContain('main--full-bleed')
  })

  it('shows breadcrumbs on paper detail routes', () => {
    routeMeta.value = { title: '论文详情' }
    routePath.value = '/papers/hss-001'
    routeName.value = RouteName.PaperDetail
    routeParams.value = { paperId: 'hss-001' }
    const wrapper = mountLayout()

    expect(wrapper.find('.el-breadcrumb-stub').exists()).toBe(true)
    expect(wrapper.text()).toContain('文献库')
    expect(wrapper.text()).toContain('论文详情')
  })

  it('renders shell nav labels, brand link, and icons', () => {
    const wrapper = mountLayout()

    expect(wrapper.text()).toContain('工作台')
    expect(wrapper.text()).toContain('文献库')
    expect(wrapper.text()).toContain('共同体巡检')
    expect(wrapper.text()).toContain('V1')
    expect(wrapper.find('.router-link-stub').attributes('href')).toBe('/')
    expect(wrapper.find('[data-testid="icon-home"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="icon-document"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="icon-search"]').exists()).toBe(true)
  })

  it('uses 240px aside for app shell', () => {
    const wrapper = mountLayout()

    expect(wrapper.find('.el-aside-stub').attributes('data-width')).toBe('240px')
  })

  it('keeps /papers nav active on paper detail routes', () => {
    routePath.value = '/papers/hss-001'
    const wrapper = mountLayout()

    expect(wrapper.find('.el-menu-stub').attributes('data-active')).toBe('/papers')
  })

  it('keeps /patrol nav active on patrol subpaths', () => {
    routePath.value = '/patrol/report'
    const wrapper = mountLayout()

    expect(wrapper.find('.el-menu-stub').attributes('data-active')).toBe('/patrol')
  })

  it('navigates via router.push when menu emits select', async () => {
    const wrapper = mountLayout()

    await wrapper.find('.el-menu-stub').trigger('click')

    expect(routerPush).toHaveBeenCalledWith('/patrol')
  })

  it('wraps routed content in route-fade transition (§8.1)', () => {
    const wrapper = mountLayout()

    expect(wrapper.find('.router-view-stub').exists()).toBe(true)
    expect(wrapper.find('.route-view-content').exists()).toBe(true)
  })

  it('shows mobile nav toggle on narrow viewport (§8.3)', async () => {
    mockMatchMedia(true)
    const wrapper = mountLayout()
    await flushPromises()

    const toggle = wrapper.find('.header-menu-toggle')
    expect(toggle.exists()).toBe(true)
    expect(toggle.attributes('aria-label')).toBe(SHELL_BASELINE_COPY.mobileNavToggleLabel)
  })

  it('opens aside drawer when mobile toggle is clicked', async () => {
    mockMatchMedia(true)
    const wrapper = mountLayout()
    await flushPromises()

    expect(wrapper.find('.aside').classes()).not.toContain('aside--open')
    await wrapper.find('.header-menu-toggle').trigger('click')
    expect(wrapper.find('.aside').classes()).toContain('aside--open')
    expect(wrapper.find('.header-menu-toggle').attributes('aria-label')).toBe(SHELL_BASELINE_COPY.mobileNavCloseLabel)
  })
})
