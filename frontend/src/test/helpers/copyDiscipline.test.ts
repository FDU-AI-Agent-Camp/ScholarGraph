import { describe, expect, it } from 'vitest'

import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { HOME_BASELINE_COPY } from '@/constants/homeCopy'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import {
  allBodySelectorsAvoidMono,
  allRegisteredSubtitlesUseSecondary,
  answerPanelTypographyMatchesBaseline,
  citationTagMixedLayout,
  citationTagUsesMonoNodeId,
  containsForbiddenEmptyPlaceholder,
  containsForbiddenMarketingWord,
  pageSubtitleUsesSecondaryColor,
  typographyChecklistPasses,
  TYPOGRAPHY_BODY_NO_MONO_SELECTORS,
} from '@/test/helpers/copyDiscipline'
import { extractStyleBlocks } from '@/test/helpers/motionDiscipline'

describe('copyDiscipline helper', () => {
  it('containsForbiddenMarketingWord detects banned terms', () => {
    expect(containsForbiddenMarketingWord('赋能科研')).toBe('赋能')
    expect(containsForbiddenMarketingWord('上传 PDF 开始自动解构')).toBeNull()
  })

  it('containsForbiddenEmptyPlaceholder rejects generic QA placeholders', () => {
    expect(containsForbiddenEmptyPlaceholder('placeholder="请输入问题"')).toBe('请输入问题')
    expect(containsForbiddenEmptyPlaceholder(DETAIL_BASELINE_COPY.qaPlaceholder)).toBeNull()
  })

  it('answerPanelTypographyMatchesBaseline checks body-lg + pre-wrap + subtle surface', () => {
    const detailView = '<div class="detail-qa__answer-panel text-body-lg"><span class="detail-qa__answer-text">'
    const styles = extractStyleBlocks(`
<style scoped>
.detail-qa__answer-panel {
  white-space: pre-wrap;
  background: var(--color-bg-subtle);
}
</style>`)
    expect(answerPanelTypographyMatchesBaseline(detailView, styles)).toBe(true)
  })

  it('citationTagMixedLayout requires label + (nodeId) with mono only on node id', () => {
    const tagVue = `
<template>
  <span class="tag-citation__label">{{ label }}</span>
  <span class="tag-citation__node-id">({{ nodeId }})</span>
</template>
<style scoped>
.tag-citation__node-id { font-family: var(--font-mono); }
</style>`
    expect(citationTagMixedLayout(tagVue)).toBe(true)
    expect(citationTagUsesMonoNodeId(extractStyleBlocks(tagVue))).toBe(true)
  })

  it('allBodySelectorsAvoidMono allows missing dedicated blocks (utility classes only)', () => {
    const styles = extractStyleBlocks(`
<style scoped>
.detail-qa__answer-text { color: var(--color-text-primary); }
</style>`)
    for (const selector of TYPOGRAPHY_BODY_NO_MONO_SELECTORS) {
      expect(allBodySelectorsAvoidMono(styles), selector).toBe(true)
    }
  })

  it('pageSubtitleUsesSecondaryColor validates hint color token', () => {
    const styles = '.papers-subtitle { color: var(--color-text-secondary); }'
    expect(pageSubtitleUsesSecondaryColor(styles, '.papers-subtitle')).toBe(true)
  })

  it('typographyChecklistPasses aggregates §1.4.4 four-item gate', () => {
    const detailView = `
<template>
<div class="detail-qa__answer-panel text-body-lg"><span class="detail-qa__answer-text"></span></div>
</template>
<style scoped>
.detail-qa__answer-panel { white-space: pre-wrap; background: var(--color-bg-subtle); }
</style>`
    const tagCitation = `
<template>
<span class="tag-citation__label"></span><span class="tag-citation__node-id">({{ nodeId }})</span>
</template>
<style scoped>.tag-citation__node-id { font-family: var(--font-mono); }</style>`

    expect(
      typographyChecklistPasses({
        detailViewSrc: detailView,
        detailStyleSrc: extractStyleBlocks(detailView),
        tagCitationSrc: tagCitation,
        papersStyleSrc: '.papers-subtitle { color: var(--color-text-secondary); }',
        homeStyleSrc: '.home-subtitle { color: var(--color-text-secondary); }',
        patrolStyleSrc: '.patrol-view__subtitle { color: var(--color-text-secondary); }',
        uploadStyleSrc: '.paper-upload__tip { color: var(--color-text-secondary); }',
      }),
    ).toBe(true)
  })

  it('baseline copy constants align with §1.4.4 table', () => {
    expect(HOME_BASELINE_COPY.eyebrow).toBe('AI AGENT · GRAPH RAG')
    expect(PAPERS_BASELINE_COPY.subtitle).toBe('管理已上传论文，查看解构进度与图谱入口')
    expect(DETAIL_BASELINE_COPY.citationLabel).toBe('引用节点')
    expect(DETAIL_BASELINE_COPY.qaPlaceholderAlt).toContain('分析视角')
  })

  it('allRegisteredSubtitlesUseSecondary reads per-view style blocks', () => {
    const styles: Record<string, string> = {
      'views/PapersView.vue': '.papers-subtitle { color: var(--color-text-secondary); }',
      'views/HomeView.vue': '.home-subtitle { color: var(--color-text-secondary); }',
      'views/PatrolView.vue': '.patrol-view__subtitle { color: var(--color-text-secondary); }',
    }
    expect(allRegisteredSubtitlesUseSecondary((path) => styles[path] ?? '')).toBe(true)
  })
})
