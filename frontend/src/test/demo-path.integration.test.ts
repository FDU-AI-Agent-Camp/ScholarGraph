/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * design-spec §16 / ui-design-progress §6 — Prototype 答辩路径验收。
 *
 * 路径树：
 *   Home → Papers → Detail(Processing/QA) → Graph → Detail
 *   Home → Patrol(Report-LensClash) → Graph(deep-link)
 */
import { describe, expect, it } from 'vitest'

import patrolLensClashFixture from '../../../docs/api/fixtures/patrol-lens-clash.json'
import papersListFixture from '../../../docs/api/fixtures/papers-list.json'
import graphFixture from '../../../docs/api/fixtures/graph-hss.json'
import type { PatrolReport, PaperSummary, UnifiedPaperGraph } from '@/api/types'
import { routes } from '@/router/index'
import { RouteName } from '@/router/meta'
import { buildHighlightStateMap, toG6GraphPayload } from '@/utils/paperGraph'
import { DESIGN_SPEC_SEMANTIC_COLORS, loadDesignTokenMap, readFrontendSource } from '@/test/helpers/designTokens'
import { answerPanelTypographyMatchesBaseline, citationTagMixedLayout } from '@/test/helpers/copyDiscipline'
import { answerPanelStyleBlockHasNoAnimation, extractStyleBlocks } from '@/test/helpers/motionDiscipline'

const DEMO_PAPER_ID = 'hss-001'
const DEMO_PATROL_PAPER_B = 'hss-002'

const homeViewSrc = readFrontendSource('views/HomeView.vue')
const papersViewSrc = readFrontendSource('views/PapersView.vue')
const paperUploadSrc = readFrontendSource('components/papers/PaperUpload.vue')
const detailViewSrc = readFrontendSource('views/PaperDetailView.vue')
const statusPanelSrc = readFrontendSource('components/papers/PaperStatusPanel.vue')
const graphViewSrc = readFrontendSource('views/PaperGraphView.vue')
const patrolViewSrc = readFrontendSource('views/PatrolView.vue')
const patrolViewHelpersSrc = readFrontendSource('utils/patrolViewHelpers.ts')
const patrolViewBundleSrc = `${patrolViewSrc}\n${patrolViewHelpersSrc}`
const tagCitationSrc = readFrontendSource('components/ui/TagCitation.vue')
const paperGraphUtilSrc = readFrontendSource('utils/paperGraph.ts')

const patrolReport = patrolLensClashFixture.data as PatrolReport
const demoPaperInList = (papersListFixture.data.items as PaperSummary[]).find((item) => item.paper_id === DEMO_PAPER_ID)

function resolveDefensePath(path: string) {
  const matched = routes.find((route) => {
    if (route.path === path) {
      return true
    }
    if (!route.path.includes(':')) {
      return false
    }
    const pattern = route.path.replace(/:[^/]+/g, '[^/]+')
    return new RegExp(`^${pattern}$`).test(path.split('?')[0] ?? path)
  })
  return matched
}

describe('design-spec §16 Prototype 答辩路径', () => {
  describe('Home → [上传论文] → Papers / Default', () => {
    it('primary CTA navigates to /papers for upload entry', () => {
      expect(homeViewSrc).toContain('HOME_BASELINE_COPY')
      expect(homeViewSrc).toContain('to="/papers"')
      expect(homeViewSrc).toMatch(/to="\/papers"/)
    })

    it('Papers page hosts upload zone and paper table for default list state', () => {
      expect(papersViewSrc).toContain('PaperUpload')
      expect(papersViewSrc).toContain('fetchList')
      expect(papersViewSrc).toContain('openDetail')
      expect(paperUploadSrc).toContain('PAPERS_BASELINE_COPY')
    })

    it('upload success routes into Detail via paper_id param', () => {
      expect(papersViewSrc).toContain('RouteName.PaperDetail')
      expect(papersViewSrc).toContain('onUploaded')
    })

    it('route table maps /papers to Papers screen', () => {
      const papersRoute = routes.find((route) => route.path === '/papers')
      expect(papersRoute?.name).toBe(RouteName.Papers)
      expect(papersRoute?.meta?.title).toBe('文献库')
    })
  })

  describe('Papers → [hss-001 详情] → Detail / Processing', () => {
    it('demo fixture lists hss-001 as the sample paper entry', () => {
      expect(demoPaperInList?.paper_id).toBe(DEMO_PAPER_ID)
      expect(demoPaperInList?.paradigm).toBe('HSS')
    })

    it('Home quick link opens example paper detail at /papers/hss-001', () => {
      expect(homeViewSrc).toContain(`to="/papers/${DEMO_PAPER_ID}"`)
      expect(homeViewSrc).toContain('打开示例论文')
    })

    it('Detail wires PaperStatusPanel for pipeline progress while not ready', () => {
      expect(detailViewSrc).toContain('PaperStatusPanel')
      expect(detailViewSrc).toContain('isGraphInteractiveStatus')
      expect(detailViewSrc).toContain('terminal-reached')
      expect(statusPanelSrc).toContain('PIPELINE_STEPS')
      expect(statusPanelSrc).toContain('status-step-pulse')
    })

    it('processing state disables QA and shows not-ready alert copy', () => {
      expect(detailViewSrc).toContain(':disabled="!isInteractive()"')
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY.notReadyAlert')
      expect(detailViewSrc).toContain('detail-graph__placeholder')
    })

    it('route table maps /papers/hss-001 to PaperDetail', () => {
      const detailRoute = resolveDefensePath(`/papers/${DEMO_PAPER_ID}`)
      expect(detailRoute?.name).toBe(RouteName.PaperDetail)
      expect(typeof detailRoute?.props).toBe('function')
    })
  })

  describe('Detail → QA-Citation-Active', () => {
    it('ready Detail exposes SSE QA, citation tags, and compact graph preview', () => {
      const qaComposableSrc = readFrontendSource('composables/usePaperDetailQa.ts')
      expect(qaComposableSrc).toContain('streamPaperQa')
      expect(detailViewSrc).toContain('usePaperDetailQa')
      expect(detailViewSrc).toContain('TagCitation')
      expect(detailViewSrc).toContain('PaperGraph')
      expect(detailViewSrc).toContain('highlightNodeId')
      expect(detailViewSrc).toContain('focusCitation')
    })

    it('fixture graph-hss aligns with demo paper_id for citation highlight chain', () => {
      const graph = graphFixture.data as UnifiedPaperGraph
      expect(graph.paper_id).toBe(DEMO_PAPER_ID)
      expect(toG6GraphPayload(graph).nodes.length).toBeGreaterThan(0)
    })

    it('behavior covered by PaperDetailView.spec §5.8 citation ↔ graph highlight tests', () => {
      const detailSpecSrc = readFrontendSource('views/PaperDetailView.spec.ts')
      expect(detailSpecSrc).toContain('activates TagCitation and graph highlight together on SSE citation')
      expect(detailSpecSrc).toContain('updates graph highlight when another citation tag is clicked')
      expect(detailSpecSrc).toContain('navigates to graph route with node query after citation highlight')
    })
  })

  describe('Detail → [全屏图谱] → Graph / Node-Selected', () => {
    it('openFullGraph pushes PaperGraph with optional node query from active citation', () => {
      expect(detailViewSrc).toContain('openFullGraph')
      expect(detailViewSrc).toContain('RouteName.PaperGraph')
      expect(detailViewSrc).toContain('query: highlightNodeId.value ? { node: highlightNodeId.value } : {}')
    })

    it('Graph page reads ?node= for deep-link selection and drawer open', () => {
      expect(graphViewSrc).toContain('route.query.node')
      expect(graphViewSrc).toContain('syncSelectionFromRoute')
      expect(graphViewSrc).toContain('GraphNodeDrawer')
      expect(graphViewSrc).toContain(':full-bleed="true"')
    })

    it('route table maps graph deep-link with fullBleed meta', () => {
      const graphRoute = resolveDefensePath(`/papers/${DEMO_PAPER_ID}/graph`)
      expect(graphRoute?.name).toBe(RouteName.PaperGraph)
      expect(graphRoute?.meta?.fullBleed).toBe(true)
    })
  })

  describe('Graph → [返回] → Detail', () => {
    it('Graph header back link returns to paper detail route', () => {
      expect(graphViewSrc).toContain('graph-view__back')
      expect(graphViewSrc).toContain(':to="`/papers/${paperId}`"')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY.backLink')
    })

    it('409 graph-not-ready CTA also returns to detail (defense fallback)', () => {
      expect(graphViewSrc).toContain('graph-view__error-cta')
      expect(graphViewSrc).toContain('backToDetail')
    })
  })

  describe('Home → [Lens Clash 演示] → Patrol / Report-LensClash', () => {
    it('Home quick card links to /patrol with Lens Clash copy', () => {
      expect(homeViewSrc).toContain('Lens Clash')
      expect(homeViewSrc).toMatch(/to="\/patrol"/)
      expect(homeViewSrc).toContain('查看巡检演示')
    })

    it('Patrol defaults to lens_clash mode and demo paper ids hss-001 / hss-002', () => {
      expect(patrolViewSrc).toContain("ref('hss-001')")
      expect(patrolViewSrc).toContain("ref('hss-002')")
      expect(patrolViewSrc).toContain("ref<PatrolMode>('lens_clash')")
      expect(patrolViewSrc).toContain('InsightCard')
    })

    it('patrol-lens-clash fixture matches Report-LensClash demo narrative', () => {
      expect(patrolReport.mode).toBe('lens_clash')
      expect(patrolReport.paper_ids).toEqual([DEMO_PAPER_ID, DEMO_PATROL_PAPER_B])
      expect(patrolReport.insights[0]?.title).toContain('Lens Clash')
      expect(patrolReport.insights[0]?.node_refs.length).toBeGreaterThan(0)
    })

    it('route table maps /patrol to Patrol screen', () => {
      const patrolRoute = routes.find((route) => route.path === '/patrol')
      expect(patrolRoute?.name).toBe(RouteName.Patrol)
      expect(patrolRoute?.meta?.title).toBe('共同体巡检')
    })
  })

  describe('Patrol → [node_ref] → Graph / Deep-Link', () => {
    it('graphLinkForNodeRef builds PaperGraph route with node query', () => {
      expect(patrolViewBundleSrc).toContain('graphLinkForNodeRef')
      expect(patrolViewBundleSrc).toContain('query: { node: ref.node_id }')
      expect(patrolViewBundleSrc).toContain('RouteName.PaperGraph')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY.nodeRefGraphLink')
    })

    it('demo node_ref from fixture targets graph deep-link ids', () => {
      const nodeRef = patrolReport.insights[0]?.node_refs[0]
      expect(nodeRef?.paper_id).toBe(DEMO_PAPER_ID)
      expect(nodeRef?.node_id).toBe('n_lens_a')
    })

    it('behavior covered by PatrolView.spec node_refs graph deep links (7.5)', () => {
      const patrolSpecSrc = readFrontendSource('views/PatrolView.spec.ts')
      expect(patrolSpecSrc).toContain('renders node_refs as graph deep links (7.5)')
      expect(patrolSpecSrc).toContain('n_lens_a')
    })
  })

  describe('必测交互：Citation Tag click ↔ Graph 节点 active（150ms）', () => {
    it('motion token budget is 150ms via --duration-fast / --transition-fast', () => {
      const tokens = loadDesignTokenMap()
      expect(tokens['--duration-fast']).toBe('150ms')
      expect(tokens['--transition-fast']).toContain('var(--duration-fast)')
    })

    it('TagCitation active state animates border/background with --transition-fast', () => {
      expect(tagCitationSrc).toContain('tag-citation--active')
      expect(tagCitationSrc).toContain('var(--transition-fast)')
      expect(tagCitationSrc).toContain('var(--color-citation-active)')
    })

    it('PaperGraph active stroke uses same citation token (#E11D48) at 120ms state animation', () => {
      const tokens = loadDesignTokenMap()
      expect(tokens['--color-citation-active']).toBe(DESIGN_SPEC_SEMANTIC_COLORS.citationActive)
      expect(paperGraphUtilSrc).toContain('GRAPH_STATE_ANIMATION_MS')
      expect(paperGraphUtilSrc).toContain("fields: ['stroke', 'lineWidth', 'fill']")
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\./)
    })

    it('SSE citation event maps to G6 active highlight on shared node_id', () => {
      const graph = graphFixture.data as UnifiedPaperGraph
      const nodeIds = toG6GraphPayload(graph).nodes.map((node) => node.id)
      const highlight = buildHighlightStateMap(nodeIds, 'n1')
      expect(highlight.n1).toBe('active')
    })

    it('Detail QA panel binds TagCitation :active to highlightNodeId for bidirectional sync', () => {
      expect(detailViewSrc).toContain("item.type === 'node' && item.node_id === highlightNodeId")
      expect(detailViewSrc).toContain('@click="focusCitation(item)"')
      expect(detailViewSrc).toContain(':highlight-node-id="highlightNodeId"')
      expect(detailViewSrc).toContain('@node-click="onGraphNodeClick"')
    })
  })

  describe('§1.4.3 动效验收 checklist', () => {
    it('Citation 点击：150ms token + 同步 highlightNodeId 绑定', () => {
      const tokens = loadDesignTokenMap()
      expect(tokens['--duration-fast']).toBe('150ms')
      expect(tagCitationSrc).toContain('var(--transition-fast)')
      expect(detailViewSrc).toContain("item.type === 'node' && item.node_id === highlightNodeId")
      expect(detailViewSrc).toContain(':highlight-node-id="highlightNodeId"')
      expect(paperGraphUtilSrc).toContain('GRAPH_STATE_ANIMATION_MS')
    })

    it('答辩路径无 transition:all（Tag + Graph 工具链）', () => {
      expect(tagCitationSrc).not.toMatch(/transition\s*:\s*all\b/i)
      expect(paperGraphUtilSrc).not.toMatch(/transition\s*:\s*all\b/i)
      expect(readFrontendSource('test/ui-antipattern.acceptance.spec.ts')).toContain('无裸 transition: all')
    })

    it('SSE 演示不遮挡阅读：答案区无 animation，图谱 labelFill 无 hover 位移', () => {
      expect(detailViewSrc).toContain('detail-qa__answer-text')
      expect(answerPanelStyleBlockHasNoAnimation(extractStyleBlocks(detailViewSrc))).toBe(true)
      expect(paperGraphUtilSrc).toContain('labelFill')
      expect(paperGraphUtilSrc).not.toMatch(/scale:\s*1\./)
      expect(readFrontendSource('components/layout/AppLayout.vue')).not.toMatch(/blur\s*\(/i)
    })
  })

  describe('§1.4.4 文案验收 checklist', () => {
    it('答辩路径引用集中 baseline copy 常量', () => {
      expect(homeViewSrc).toContain('HOME_BASELINE_COPY')
      expect(readFrontendSource('views/PapersView.vue')).toContain('PAPERS_BASELINE_COPY')
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY')
    })

    it('Upload 失败与 Empty 态含可行动文案', () => {
      const uploadSrc = readFrontendSource('components/papers/PaperUpload.vue')
      expect(uploadSrc).toContain('uploadRetryHint')
      expect(uploadSrc).toContain('paper-upload__retry')
      expect(readFrontendSource('test/ui-phase144-copy.acceptance.spec.ts')).toContain(
        '§1.4.4 Copy & typography discipline',
      )
    })
  })

  describe('§1.4.4 排版验收 checklist', () => {
    it('Detail SSE 答案区 Body-lg + pre-wrap + 灰底可读', () => {
      const detailStyles = extractStyleBlocks(detailViewSrc)
      expect(answerPanelTypographyMatchesBaseline(detailViewSrc, detailStyles)).toBe(true)
    })

    it('Citation Tag label + (node_id) mono 混排', () => {
      expect(citationTagMixedLayout(readFrontendSource('components/ui/TagCitation.vue'))).toBe(true)
    })

    it('答辩路径副标题 / upload hint 使用 secondary 色', () => {
      expect(extractStyleBlocks(readFrontendSource('views/PapersView.vue'))).toMatch(
        /\.papers-subtitle[\s\S]*color: var\(--color-text-secondary\)/,
      )
      expect(extractStyleBlocks(readFrontendSource('components/papers/PaperUpload.vue'))).toMatch(
        /\.paper-upload__tip[\s\S]*color: var\(--color-text-secondary\)/,
      )
    })
  })

  describe('§1.5 设计参数 — demo-path 答辩锚点', () => {
    it('Citation #E11D48 + 150ms 与 Shell 240/56 在答辩链路透传', () => {
      const tokens = loadDesignTokenMap()
      expect(tokens['--color-citation-active']).toBe('#e11d48')
      expect(tokens['--content-max-width']).toBe('1280px')
      expect(readFrontendSource('components/layout/AppLayout.vue')).toContain('width="240px"')
      expect(readFrontendSource('test/ui-design-foundation.acceptance.spec.ts')).toContain('§1.5 设计参数速查')
    })
  })

  describe('§1.4 四维 — 答辩路径目视检查锚点', () => {
    it('background: shell/page/surface/canvas tokens present on defense screens', () => {
      expect(readFrontendSource('components/layout/AppLayout.vue')).toContain('var(--color-bg-page)')
      expect(homeViewSrc).toContain('var(--color-bg-surface)')
      expect(graphViewSrc).toContain('var(--color-bg-canvas)')
      expect(patrolViewSrc).toContain('page-card')
    })

    it('layout: Detail dual-column + Graph full-bleed preserved on defense branch', () => {
      expect(detailViewSrc).toContain('detail-layout')
      expect(detailViewSrc).toContain('grid-template-columns: 45fr 55fr')
      expect(detailViewSrc).toContain('gap: var(--spacing-24)')
      expect(detailViewSrc.indexOf('PaperMetadataCard')).toBeLessThan(detailViewSrc.indexOf('PaperStatusPanel'))
      expect(detailViewSrc.indexOf('PaperStatusPanel')).toBeLessThan(detailViewSrc.indexOf('detail-qa'))
      expect(graphViewSrc).toContain('min-height: 720px')
    })

    it('motion: Citation 150ms + route-fade + reduced-motion on defense branch', () => {
      expect(readFrontendSource('assets/main.css')).toContain(':focus-visible')
      expect(readFrontendSource('components/ui/TagCitation.vue')).toContain('var(--transition-fast)')
      expect(readFrontendSource('components/layout/AppLayout.vue')).toContain('route-fade')
      expect(detailViewSrc).toContain('highlightNodeId')
    })

    it('layout: Home asymmetric grids + shell inset padding on defense path', () => {
      expect(homeViewSrc).toContain('grid-template-columns: 58fr 42fr')
      expect(homeViewSrc).toContain('grid-template-columns: 60fr 40fr')
      const appLayoutStyles = readFrontendSource('components/layout/AppLayout.vue')
      expect(appLayoutStyles).toContain('padding: var(--spacing-24) var(--spacing-32)')
    })

    it('motion: route-fade + reduced-motion hooks exist for cross-page continuity', () => {
      const appLayoutSrc = readFrontendSource('components/layout/AppLayout.vue')
      expect(appLayoutSrc).toContain('route-fade')
      expect(appLayoutSrc).toContain('prefers-reduced-motion')
    })

    it('copy: defense screens use baseline constants (not placeholder scaffolding)', () => {
      expect(homeViewSrc).not.toContain('请输入内容')
      expect(detailViewSrc).toContain('DETAIL_BASELINE_COPY')
      expect(graphViewSrc).toContain('GRAPH_BASELINE_COPY')
      expect(patrolViewSrc).toContain('PATROL_BASELINE_COPY')
    })
  })

  describe('full route walkthrough (smoke)', () => {
    it('matches defense URLs to route records in presentation order', () => {
      const nodeRef = patrolReport.insights[0]?.node_refs[0]
      const steps: Array<{ path: string; name: string | symbol | null | undefined }> = [
        { path: '/', name: RouteName.Home },
        { path: '/papers', name: RouteName.Papers },
        { path: `/papers/${DEMO_PAPER_ID}`, name: RouteName.PaperDetail },
        { path: `/papers/${DEMO_PAPER_ID}/graph`, name: RouteName.PaperGraph },
        { path: `/papers/${DEMO_PAPER_ID}`, name: RouteName.PaperDetail },
        { path: '/patrol', name: RouteName.Patrol },
        {
          path: `/papers/${nodeRef?.paper_id}/graph`,
          name: RouteName.PaperGraph,
        },
      ]

      for (const step of steps) {
        const route =
          step.path === '/' || step.path === '/papers' || step.path === '/patrol'
            ? routes.find((entry) => entry.path === step.path)
            : resolveDefensePath(step.path)
        expect(route?.name, step.path).toBe(step.name)
      }
    })
  })
})
