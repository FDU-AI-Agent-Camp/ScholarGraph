import { ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AppLayout from '@/components/layout/AppLayout.vue'

const routeMeta = ref<{ title?: string }>({ title: '文献库' })
const routePath = ref('/papers')
const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({
    get path() {
      return routePath.value
    },
    get meta() {
      return routeMeta.value
    },
  }),
  useRouter: () => ({
    push: routerPush,
  }),
}))

function mountLayout(): VueWrapper {
  return mount(AppLayout, {
    global: {
      stubs: {
        'el-container': { template: '<div class="el-container-stub"><slot /></div>' },
        'el-aside': {
          props: ['width'],
          template: '<aside class="el-aside-stub" :data-width="width"><slot /></aside>',
        },
        'el-header': { template: '<header class="el-header-stub"><slot /></header>' },
        'el-main': { template: '<main class="el-main-stub"><slot /></main>' },
        'el-menu': {
          props: ['defaultActive'],
          emits: ['select'],
          template:
            '<nav class="el-menu-stub" :data-active="defaultActive" @click="$emit(\'select\', \'/patrol\')"><slot /></nav>',
        },
        'el-menu-item': { template: '<div class="el-menu-item-stub"><slot /></div>' },
        'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
        'el-link': { template: '<a class="el-link-stub"><slot /></a>' },
        'router-link': { props: ['to'], template: '<a class="router-link-stub" :href="to"><slot /></a>' },
        'router-view': true,
        HomeFilled: { template: '<svg data-testid="icon-home" />' },
        Document: { template: '<svg data-testid="icon-document" />' },
        Search: { template: '<svg data-testid="icon-search" />' },
      },
    },
  })
}

describe('AppLayout', () => {
  beforeEach(() => {
    routeMeta.value = { title: '文献库' }
    routePath.value = '/papers'
    routerPush.mockClear()
  })

  it('shows route meta title in header', () => {
    const wrapper = mountLayout()

    expect(wrapper.text()).toContain('文献库')
    expect(wrapper.text()).toContain('学术论文逻辑解构')
  })

  it('falls back when meta title is missing', () => {
    routeMeta.value = {}
    const wrapper = mountLayout()

    expect(wrapper.text()).toContain('ScholarGraph')
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
})
