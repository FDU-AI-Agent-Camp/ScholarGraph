import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'

const mockRunPatrol = vi.fn()

vi.mock('@/api/patrol', () => ({
  runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
}))

import PatrolView from '@/views/PatrolView.vue'

describe('PatrolView', () => {
  it('shows narrowed ApiClientError in alert', async () => {
    mockRunPatrol.mockRejectedValue(
      new ApiClientError({ code: 'PATROL_FAILED', message: '巡检失败' }, 500),
    )

    const wrapper = mount(PatrolView, {
      global: {
        stubs: {
          'el-input': true,
          'el-button': { template: '<button @click="$attrs.onClick?.()"><slot /></button>' },
          'el-alert': {
            props: ['title'],
            template: '<div class="patrol-error" :data-title="title" />',
          },
          'el-collapse': true,
          'el-collapse-item': true,
          'el-tag': true,
        },
      },
    })

    await wrapper.find('button').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.patrol-error')
    expect(alert.attributes('data-title')).toBe('巡检失败')
  })
})
