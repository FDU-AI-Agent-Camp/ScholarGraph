import { config } from '@vue/test-utils'
import { vi } from 'vitest'

config.global.stubs = {
  'el-card': {
    template:
      '<div class="el-card-stub"><slot name="header" /><slot /></div>',
  },
  'el-progress': true,
  'el-alert': {
    props: ['title', 'description', 'type', 'closable', 'showIcon'],
    template:
      '<div class="el-alert-stub" :data-type="type" :data-title="title" :data-description="description" />',
  },
  'el-button': {
    template: '<button type="button" class="el-button-stub"><slot /></button>',
  },
}

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
}))
