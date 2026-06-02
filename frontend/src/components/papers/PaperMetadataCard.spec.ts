import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ParadigmClassification } from '@/api/types'
import PaperMetadataCard from '@/components/papers/PaperMetadataCard.vue'
import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'

const classification: ParadigmClassification = {
  paradigm: 'HSS',
  confidence: 0.95,
  reason: '历史制度主义视角，属于典型的人文社科规范。',
}

describe('PaperMetadataCard', () => {
  it('renders nothing when classification is absent', () => {
    const wrapper = mount(PaperMetadataCard, {
      props: { classification: null },
      global: {
        stubs: {
          'el-collapse': true,
          'el-collapse-item': true,
        },
      },
    })

    expect(wrapper.find('.metadata-card').exists()).toBe(false)
  })

  it('renders collapsible metadata with confidence and classification reason toggle', async () => {
    const wrapper = mount(PaperMetadataCard, {
      props: { classification },
      global: {
        stubs: {
          'el-collapse': {
            template: '<div class="collapse-stub"><slot /></div>',
          },
          'el-collapse-item': {
            props: ['title', 'name'],
            template: '<div class="collapse-item-stub"><h3>{{ title }}</h3><slot /></div>',
          },
          'el-progress': true,
          BadgeParadigm: {
            props: ['paradigm'],
            template: '<span class="badge-paradigm-stub">{{ paradigm }}</span>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain(DETAIL_BASELINE_COPY.metadataTitle)
    expect(wrapper.text()).toContain('95%')
    expect(wrapper.find('.badge-paradigm-stub').text()).toBe('HSS')

    expect(wrapper.find('.metadata-card__reason-text').exists()).toBe(false)
    await wrapper.find('.metadata-card__reason-toggle').trigger('click')
    expect(wrapper.find('.metadata-card__reason-toggle').text()).toBe(DETAIL_BASELINE_COPY.showClassificationReason)
  })
})
