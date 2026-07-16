import '@/styles/tokens.css'

import { config } from '@vue/test-utils'
import type { Directive } from 'vue'
import { vi } from 'vitest'

/** Element Plus `v-loading` — no-op in unit tests to avoid Vue resolve warnings. */
const loadingDirective: Directive = {
  mounted(el, binding) {
    if (binding.value) {
      el.setAttribute('data-loading', 'true')
    }
  },
  updated(el, binding) {
    if (binding.value) {
      el.setAttribute('data-loading', 'true')
    } else {
      el.removeAttribute('data-loading')
    }
  },
}

config.global.directives = {
  loading: loadingDirective,
}

config.global.stubs = {
  'el-card': {
    template: '<div class="el-card-stub"><slot name="header" /><slot /></div>',
  },
  'el-progress': true,
  'el-alert': {
    props: ['title', 'description', 'type', 'closable', 'showIcon'],
    template: '<div class="el-alert-stub" :data-type="type" :data-title="title" :data-description="description" />',
  },
  'el-button': {
    template: '<button type="button" class="el-button-stub"><slot /></button>',
  },
}

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
