/**
 * Phase 7 Patrol acceptance (7.1–7.6) — design-spec §11 + ui-design-progress §1.4.4.
 */
import { describe, expect, it } from 'vitest'

import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { RouteName } from '@/router/meta'
import { loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import { resolvePatrolApiError } from '@/utils/patrolForm'

const patrolViewSrc = readFrontendSource('views/PatrolView.vue')
const patrolViewHelpersSrc = readFrontendSource('utils/patrolViewHelpers.ts')
const patrolViewBundleSrc = `${patrolViewSrc}\n${patrolViewHelpersSrc}`
const patrolCopySrc = readFrontendSource('constants/patrolCopy.ts')
const patrolFormSrc = readFrontendSource('utils/patrolForm.ts')
const insightCardSrc = readFrontendSource('components/ui/InsightCard.vue')

describe('Phase 7 Patrol acceptance (7.1–7.6)', () => {
  describe('7.1 page header H1 and baseline subtitle', () => {
    it('uses PATROL_BASELINE_COPY for title and subtitle', () => {
      expect(PATROL_BASELINE_COPY.pageTitle).toBe('共同体巡检')
      expect(PATROL_BASELINE_COPY.subtitle).toBe('跨论文探测理论视角冲突与论点矛盾 · 需 2 篇 ready 论文')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.pageTitle')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.subtitle')
      expect(patrolViewSrc).toContain('text-h1 patrol-view__title')
    })
  })

  describe('7.2 dual paper selects and duplicate warning copy', () => {
    it('wires paper A/B selects and duplicate validation baseline', () => {
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.paperLabelA')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.paperLabelB')
      expect(patrolViewSrc).toContain('el-select')
      expect(patrolFormSrc).toContain('validatePatrolSelection')
      expect(patrolCopySrc).toContain('validationDuplicate')
      expect(patrolCopySrc).toContain('validationExactTwo')
    })
  })

  describe('7.3 segmented control with primary active background', () => {
    it('renders custom segmented control with primary active state', () => {
      expect(patrolViewSrc).toContain('patrol-mode-segment')
      expect(patrolViewSrc).toContain('patrol-mode-segment__item--active')
      expect(patrolViewSrc).toContain('background: var(--color-primary)')
      expect(patrolViewBundleSrc).toContain('PATROL_BASELINE_COPY.modeLensClashCaption')
      expect(patrolViewBundleSrc).toContain('PATROL_BASELINE_COPY.modeContradictionCaption')
    })
  })

  describe('7.4 run button baseline and loading copy', () => {
    it('uses baseline run label and loading text', () => {
      expect(PATROL_BASELINE_COPY.runButton).toBe('运行巡检')
      expect(PATROL_BASELINE_COPY.runButtonLoading).toBe('分析中…')
      expect(patrolViewSrc).toContain('runButtonLoading')
      expect(patrolViewSrc).toContain('runButton')
    })
  })

  describe('7.5 InsightCard node_refs link to graph ?node=', () => {
    it('links node refs through RouterLink with PaperGraph route query', () => {
      expect(patrolViewSrc).toContain('InsightCard')
      expect(patrolViewBundleSrc).toContain('RouteName.PaperGraph')
      expect(patrolViewBundleSrc).toContain('query: { node: ref.node_id }')
      expect(insightCardSrc).toContain('insight-card--lens_clash')
      expect(insightCardSrc).toContain('insight-card--contradiction')
    })
  })

  describe('7.6 error alert title and CTA from baseline table', () => {
    it('maps API errors through resolvePatrolApiError with CTA actions', () => {
      expect(patrolFormSrc).toContain('resolvePatrolApiError')
      expect(patrolCopySrc).toContain(PATROL_BASELINE_COPY.graphNotReadyTitle)
      expect(patrolCopySrc).toContain(PATROL_BASELINE_COPY.insufficientDataTitle)
      expect(patrolViewSrc).toContain('patrol-view__error-cta')
      expect(patrolViewSrc).toContain('RouteName.Papers')
      expect(patrolViewSrc).toContain('resetPaperSelection')
    })
  })

  describe('Phase 7 acceptance checklist (ui-design-progress §验收)', () => {
    it('checklist: PatrolView.spec and patrol.integration test files cover patrol flow', () => {
      const patrolViewSpecSrc = readFrontendSource('views/PatrolView.spec.ts')
      const patrolIntegrationSrc = readFrontendSource('test/patrol.integration.test.ts')
      const patrolFormTestSrc = readFrontendSource('utils/patrolForm.test.ts')

      expect(patrolViewSpecSrc).toContain('baseline page header and subtitle')
      expect(patrolViewSpecSrc).toContain('duplicate paper id warning')
      expect(patrolViewSpecSrc).toContain('node_refs as graph deep links')
      expect(patrolViewSpecSrc).toContain('baseline run button label before loading')
      expect(patrolViewSpecSrc).toContain('passes lens_clash report mode variant to InsightCard')
      expect(patrolViewSpecSrc).toContain('passes contradiction report mode variant to InsightCard')
      expect(patrolIntegrationSrc).toContain('patrol-lens-clash fixture')
      expect(patrolIntegrationSrc).toContain('§1.4.4 baseline copy table matches patrolCopy constants')
      expect(patrolFormTestSrc).toContain('resolvePatrolApiError')
    })

    it('§1.4.4: subtitle, run button, and error table align with patrolCopy baseline', () => {
      expect(PATROL_BASELINE_COPY.subtitle).toBe('跨论文探测理论视角冲突与论点矛盾 · 需 2 篇 ready 论文')
      expect(PATROL_BASELINE_COPY.runButton).toBe('运行巡检')
      expect(PATROL_BASELINE_COPY.runButtonLoading).toBe('分析中…')
      expect(PATROL_BASELINE_COPY.validationExactTwo).toBe('请输入恰好 2 个 paper_id')

      const graphNotReady = resolvePatrolApiError('GRAPH_NOT_READY', '图谱未就绪')
      expect(graphNotReady.title).toBe('图谱未就绪')
      expect(graphNotReady.ctaLabel).toBe(PATROL_BASELINE_COPY.graphNotReadyCta)

      const insufficientData = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '数据不足')
      expect(insufficientData.title).toBe('数据不足')
      expect(insufficientData.description).toBe('换用 ready 状态的论文再试')
      expect(insufficientData.ctaLabel).toBe(PATROL_BASELINE_COPY.insufficientDataCta)

      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.subtitle')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.runButton')
      expect(patrolViewSrc).toContain('resolvePatrolApiError')
    })

    it('§1.4.4 / design-spec §11: insight cards distinguish lens_clash and contradiction left borders', () => {
      const tokens = loadDesignTokenMap()

      expect(insightCardSrc).toContain('border-left: 4px solid #ca8a04')
      expect(insightCardSrc).toContain('border-left: 4px solid var(--color-error)')
      expect(tokens['--color-error']).toBe('#dc2626')
      expect(patrolViewSrc).toContain(':variant="report.mode"')

      const uiSpecSrc = readFrontendSource('components/ui/ui.spec.ts')
      expect(uiSpecSrc).toContain('design-spec left border colors')
      expect(RouteName.Patrol).toBe('patrol')
    })
  })
})
