import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AppLayout from '@/components/layout/AppLayout.vue'

const routeMeta = ref<{ title?: string }>({ title: '文献库' })
const routePath = ref('/papers')

vi.mock('vue-router', () => ({
  useRoute: () => ({
    get path() {
      return routePath.value
    },
    get meta() {
      return routeMeta.value
    },
  }),
}))

describe('AppLayout', () => {
  it('shows route meta title in header', () => {
    routeMeta.value = { title: '文献库' }
    const wrapper = mount(AppLayout, {
      global: {
        stubs: {
          'el-container': { template: '<div><slot /></div>' },
          'el-aside': { template: '<div><slot /></div>' },
          'el-header': { template: '<header><slot /></header>' },
          'el-main': { template: '<main><slot /></main>' },
          'el-menu': { template: '<nav><slot /></nav>' },
          'el-menu-item': true,
          'el-link': true,
          'router-link': { template: '<a><slot /></a>' },
          'router-view': true,
        },
      },
    })

    expect(wrapper.text()).toContain('文献库')
    expect(wrapper.text()).toContain('学术论文逻辑解构')
  })

  it('falls back when meta title is missing', () => {
    routeMeta.value = {}
    const wrapper = mount(AppLayout, {
      global: {
        stubs: {
          'el-container': { template: '<div><slot /></div>' },
          'el-aside': { template: '<div><slot /></div>' },
          'el-header': { template: '<header><slot /></header>' },
          'el-main': { template: '<main><slot /></main>' },
          'el-menu': { template: '<nav><slot /></nav>' },
          'el-menu-item': true,
          'el-link': true,
          'router-link': { template: '<a><slot /></a>' },
          'router-view': true,
        },
      },
    })

    expect(wrapper.text()).toContain('ScholarGraph')
  })
})
