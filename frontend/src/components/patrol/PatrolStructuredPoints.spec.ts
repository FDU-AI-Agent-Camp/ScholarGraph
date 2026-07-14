/**
 * Unit / component — Part F / F2+F12.
 * Mounts the production PatrolStructuredPoints module with OpenAPI fixtures.
 */
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { DataResponse, PatrolInsight, PatrolPoint, PatrolReport } from '@/api/types'
import patrolClaimEvolutionFixture from '../../../../docs/api/fixtures/patrol-claim-evolution.json'
import patrolLensClashFixture from '../../../../docs/api/fixtures/patrol-lens-clash.json'
import patrolMethodOverlapFixture from '../../../../docs/api/fixtures/patrol-method-overlap.json'

const STRUCTURED_POINTS_VUE = resolve(dirname(fileURLToPath(import.meta.url)), 'PatrolStructuredPoints.vue')

function pointsFromFixture(fixture: DataResponse<PatrolReport>): PatrolPoint[] {
  const insight = fixture.data.insights[0] as PatrolInsight | undefined
  if (!insight) {
    throw new Error('fixture missing insights[0]')
  }
  return insight.structured_points ?? []
}

async function loadPatrolStructuredPoints() {
  // Absolute file URL + @vite-ignore: suite can collect before the module exists (RED).
  const mod = await import(/* @vite-ignore */ pathToFileURL(STRUCTURED_POINTS_VUE).href)
  expect(mod.default, 'PatrolStructuredPoints.vue must export a default component').toBeTruthy()
  return mod as { default: object }
}

const mountOptions = {
  global: {
    stubs: {
      RouterLink: {
        props: ['to'],
        template: '<a class="router-link-stub" :data-to="JSON.stringify(to)"><slot /></a>',
      },
    },
  },
}

describe('PatrolStructuredPoints (F2 unit)', () => {
  it('renders MethodOverlapPoint structured fields from V2 fixture', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()
    const points = pointsFromFixture(patrolMethodOverlapFixture as DataResponse<PatrolReport>)

    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...mountOptions })

    expect(wrapper.text()).toContain('PCA')
    expect(wrapper.text()).toContain('Applied PCA to MNIST pixel vectors before k-NN classification')
    expect(wrapper.text()).toContain('Principal Component Analysis compressed MNIST features to 50 dimensions')
    expect(wrapper.text()).toContain('MNIST')
    expect(wrapper.text()).toMatch(/0\.99/)
    expect(wrapper.text()).toContain('semantic')
    expect(wrapper.text()).toContain('同义词方法标签在共享 MNIST 数据集上共振')
  })

  it('renders ClaimEvolutionPoint structured fields from V2 fixture', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()
    const points = pointsFromFixture(patrolClaimEvolutionFixture as DataResponse<PatrolReport>)

    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...mountOptions })

    expect(wrapper.text()).toContain('PCA 是否提升 MNIST 分类准确率？')
    expect(wrapper.text()).toContain('PCA 将 MNIST 特征压缩至 50 维后分类准确率提升 3%')
    expect(wrapper.text()).toContain('主成分分析在 MNIST 上保留 95% 方差，分类性能与基线相当')
    expect(wrapper.text()).toContain('refined')
    expect(wrapper.text()).toMatch(/82/)
  })

  it('renders LensClashPoint structured fields from V1 fixture', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()
    const points = pointsFromFixture(patrolLensClashFixture as DataResponse<PatrolReport>)

    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...mountOptions })

    expect(wrapper.text()).toContain('消费社会')
    expect(wrapper.text()).toContain('公共领域')
    expect(wrapper.text()).toContain('ontology')
  })

  it('renders an empty points list without crashing (boundary)', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()

    const wrapper = mount(PatrolStructuredPoints, { props: { points: [] }, ...mountOptions })

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).not.toContain('PCA')
  })

  it('ignores unknown mode discriminators without throwing (boundary)', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()
    const roguePoints = [
      { mode: 'not_a_real_mode', overlap_label: 'SHOULD_NOT_SURFACE' },
    ] as unknown as PatrolInsight['structured_points']

    expect(() => mount(PatrolStructuredPoints, { props: { points: roguePoints ?? [] }, ...mountOptions })).not.toThrow()
  })

  it('renders ContradictionPoint structured fields (F12)', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()
    const points: PatrolPoint[] = [
      {
        mode: 'contradiction',
        point_a: '零工是剥削',
        point_b: '零工是自主',
        conflict_type: 'normative',
      },
    ]

    const wrapper = mount(PatrolStructuredPoints, { props: { points }, ...mountOptions })

    expect(wrapper.html()).toContain('patrol-point-card--contradiction')
    expect(wrapper.text()).toContain('零工是剥削')
    expect(wrapper.text()).toContain('零工是自主')
    expect(wrapper.text()).toContain('normative')
  })

  it('does not surface unknown-mode payload fields in the DOM (越权)', async () => {
    const { default: PatrolStructuredPoints } = await loadPatrolStructuredPoints()
    const roguePoints = [
      { mode: 'not_a_real_mode', overlap_label: 'SHOULD_NOT_SURFACE' },
    ] as unknown as PatrolInsight['structured_points']

    const wrapper = mount(PatrolStructuredPoints, { props: { points: roguePoints ?? [] }, ...mountOptions })
    expect(wrapper.text()).not.toContain('SHOULD_NOT_SURFACE')
  })
})
