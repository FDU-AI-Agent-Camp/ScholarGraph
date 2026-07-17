/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * ui-design-progress §1.4.4 — 文案与排版（基准表 / 禁止词 / 排版验收）
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { DETAIL_BASELINE_COPY } from '@/constants/detailCopy'
import { GRAPH_BASELINE_COPY } from '@/constants/graphCopy'
import { HOME_BASELINE_COPY } from '@/constants/homeCopy'
import { PAPERS_BASELINE_COPY } from '@/constants/papersCopy'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { EMPTY_STATE_PRESETS } from '@/components/ui/emptyStatePresets'
import {
  answerPanelTypographyMatchesBaseline,
  citationTagMixedLayout,
  citationTagUsesMonoNodeId,
  containsForbiddenEmptyPlaceholder,
  containsForbiddenMarketingWord,
  FORBIDDEN_MARKETING_WORDS,
  pageSubtitleUsesSecondaryColor,
  typographyChecklistPasses,
} from '@/test/helpers/copyDiscipline'
import { extractStyleBlocks } from '@/test/helpers/motionDiscipline'
import { PIPELINE_STEPS } from '@/utils/pipelineSteps'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSrc(relativePathFromSrc: string): string {
  return readFileSync(resolve(FRONTEND_SRC, relativePathFromSrc), 'utf8')
}

function collectSourceFiles(relativeDir: string, extensions: string[]): string[] {
  const absoluteDir = resolve(FRONTEND_SRC, relativeDir)
  const files: string[] = []

  for (const entry of readdirSync(absoluteDir)) {
    const fullPath = join(absoluteDir, entry)
    if (statSync(fullPath).isDirectory()) {
      files.push(...collectSourceFiles(join(relativeDir, entry), extensions))
    } else if (extensions.some((ext) => entry.endsWith(ext))) {
      files.push(join(relativeDir, entry).replace(/\\/g, '/'))
    }
  }

  return files
}

describe('§1.4.4 Copy & typography discipline', () => {
  describe('各页文案基准表', () => {
    it('Home — eyebrow / title / CTAs wired via HOME_BASELINE_COPY', () => {
      const homeSrc = readSrc('views/HomeView.vue')
      expect(homeSrc).toContain('HOME_BASELINE_COPY')
      expect(HOME_BASELINE_COPY.eyebrow).toBe('AI AGENT · GRAPH RAG')
      expect([...HOME_BASELINE_COPY.titleLines]).toEqual(['解构论文逻辑，', '发现学术共同体'])
      expect(HOME_BASELINE_COPY.primaryCta).toBe('上传论文')
      expect(HOME_BASELINE_COPY.secondaryCta).toBe('浏览文献库')
      expect(HOME_BASELINE_COPY.subtitle).toMatch(/人文社科.*理工科|理工科.*人文社科/)
    })

    it('Papers — H1 副文案 / Upload / Empty baseline', () => {
      const papersSrc = readSrc('views/PapersView.vue')
      const uploadSrc = readSrc('components/papers/PaperUpload.vue')
      expect(papersSrc).toContain('PAPERS_BASELINE_COPY')
      expect(uploadSrc).toContain('PAPERS_BASELINE_COPY')
      expect(PAPERS_BASELINE_COPY.subtitle).toBe('管理已上传论文，查看解构进度与图谱入口')
      expect(PAPERS_BASELINE_COPY.uploadMain).toBe('拖拽 PDF 到此处，或')
      expect(PAPERS_BASELINE_COPY.uploadClick).toBe('点击上传')
      expect(PAPERS_BASELINE_COPY.uploadTip).toBe('建议 ≤32MB · 上传后自动进入解构流水线')
      expect(EMPTY_STATE_PRESETS['no-papers'].title).toBe(PAPERS_BASELINE_COPY.emptyTitle)
      expect(EMPTY_STATE_PRESETS['no-papers'].description).toBe(PAPERS_BASELINE_COPY.emptyBody)
    })

    it('Detail — Alert / Step / Citation / QA placeholder baseline', () => {
      const detailSrc = readSrc('views/PaperDetailView.vue')
      expect(detailSrc).toContain('DETAIL_BASELINE_COPY')
      expect(DETAIL_BASELINE_COPY.notReadyAlert).toBe('论文尚未 ready，问答与图谱预览将在流水线完成后可用。')
      expect(PIPELINE_STEPS.map((step) => step.label)).toEqual([
        '正在解析 PDF',
        '精炼文档头部',
        '范式分类',
        '抽取图谱',
        '写入存储',
        '建图完成',
      ])
      expect(DETAIL_BASELINE_COPY.refreshCaption).toBe('每 2 秒自动刷新')
      expect(DETAIL_BASELINE_COPY.citationLabel).toBe('引用节点')
      expect(DETAIL_BASELINE_COPY.qaPlaceholder).toContain('核心论点')
      expect(DETAIL_BASELINE_COPY.qaPlaceholderAlt).toContain('分析视角')
    })

    it('Graph — H1 + 409 错误文案 baseline', () => {
      expect(GRAPH_BASELINE_COPY.pageTitle).toBe('逻辑图谱')
      expect(GRAPH_BASELINE_COPY.graphNotReadyTitle).toBe('图谱未就绪')
      expect(readSrc('views/PaperGraphView.vue')).toContain('GRAPH_BASELINE_COPY.graphNotReadyCta')
    })

    it('Patrol — 副文案 / 主按钮 / 数据不足 baseline', () => {
      expect(PATROL_BASELINE_COPY.subtitle).toBe(
        '跨论文四模式巡检（视角冲突、论点矛盾、方法重叠、观点演进）· 需 2 篇 ready 论文',
      )
      expect(PATROL_BASELINE_COPY.runButton).toBe('运行巡检')
      expect(PATROL_BASELINE_COPY.runButtonLoading).toBe('分析中…')
      expect(PATROL_BASELINE_COPY.insufficientDataTitle).toBe('数据不足')
      expect(PATROL_BASELINE_COPY.insufficientDataDescription).toBe('换用 ready 状态的论文再试')
    })
  })

  describe('禁止词表', () => {
    it('views + constants 不含 §1.4.4 营销黑话', () => {
      const sources = [
        ...collectSourceFiles('views', ['.vue']),
        ...collectSourceFiles('constants', ['.ts']),
        ...collectSourceFiles('components', ['.vue']),
      ]
      for (const relativePath of sources) {
        const src = readSrc(relativePath)
        const hit = containsForbiddenMarketingWord(src)
        expect(hit, `${relativePath} must not contain "${hit}"`).toBeNull()
      }
      expect(FORBIDDEN_MARKETING_WORDS.length).toBeGreaterThanOrEqual(10)
    })

    it('无空泛 placeholder（请输入… / 请输入问题）', () => {
      const copySources = [...collectSourceFiles('views', ['.vue']), ...collectSourceFiles('constants', ['.ts'])]
      for (const relativePath of copySources) {
        const src = readSrc(relativePath)
        const hit = containsForbiddenEmptyPlaceholder(src)
        expect(hit, `${relativePath} must not contain "${hit}"`).toBeNull()
      }
    })
  })

  describe('错误 / 空态文案 — 原因 + 行动', () => {
    it('Upload 失败按 error_code 展示并可重试', () => {
      const uploadSrc = readSrc('components/papers/PaperUpload.vue')
      expect(uploadSrc).toContain('uploadErrorCode')
      expect(uploadSrc).toContain('error.code')
      expect(uploadSrc).toContain('PAPERS_BASELINE_COPY.uploadRetryHint')
      expect(uploadSrc).toContain('paper-upload__retry')
      expect(uploadSrc).not.toContain('操作失败')
    })

    it('Graph 409 / Patrol 数据不足 / QA disabled 含下一步', () => {
      expect(readSrc('views/PaperGraphView.vue')).toContain('graph-view__error-cta')
      expect(readSrc('views/PatrolView.vue')).toContain('patrol-view__error-cta')
      expect(readSrc('views/PaperDetailView.vue')).toContain('DETAIL_BASELINE_COPY.notReadyAlert')
      expect(readSrc('views/PapersView.vue')).toContain('papers-empty')
    })
  })

  describe('§1.4.4 排版验收 — checklist', () => {
    it('问答答案区：Body-lg + pre-wrap + 内嵌灰底，长答案可读', () => {
      const detailViewSrc = readSrc('views/PaperDetailView.vue')
      const detailStyles = extractStyleBlocks(detailViewSrc)
      expect(answerPanelTypographyMatchesBaseline(detailViewSrc, detailStyles)).toBe(true)
      expect(readSrc('views/PaperDetailView.spec.ts')).toContain('§1.4.4 typography checklist')
    })

    it('副标题 / hint 用 --color-text-secondary，不抢 H1', () => {
      const papersStyles = extractStyleBlocks(readSrc('views/PapersView.vue'))
      const homeStyles = extractStyleBlocks(readSrc('views/HomeView.vue'))
      const patrolStyles = extractStyleBlocks(readSrc('views/PatrolView.vue'))
      const uploadStyles = extractStyleBlocks(readSrc('components/papers/PaperUpload.vue'))
      expect(pageSubtitleUsesSecondaryColor(papersStyles, '.papers-subtitle')).toBe(true)
      expect(pageSubtitleUsesSecondaryColor(homeStyles, '.home-subtitle')).toBe(true)
      expect(pageSubtitleUsesSecondaryColor(patrolStyles, '.patrol-view__subtitle')).toBe(true)
      expect(uploadStyles).toMatch(/\.paper-upload__tip[\s\S]*color: var\(--color-text-secondary\)/)
      expect(papersStyles).toMatch(/\.papers-title[\s\S]*color: var\(--color-text-primary\)/)
    })

    it('Mono 仅 ID / code，正文不整段 Mono', () => {
      expect(citationTagUsesMonoNodeId(extractStyleBlocks(readSrc('components/ui/TagCitation.vue')))).toBe(true)
      const detailStyles = extractStyleBlocks(readSrc('views/PaperDetailView.vue'))
      expect(detailStyles).not.toMatch(/\.detail-qa__answer-text[\s\S]*font-family: var\(--font-mono\)/)
      expect(extractStyleBlocks(readSrc('components/ui/EmptyState.vue'))).not.toMatch(
        /\.empty-state__body[\s\S]*font-family: var\(--font-mono\)/,
      )
    })

    it('中文与英文/ID 混排：label 正文 + (node_id) Mono 括号', () => {
      expect(citationTagMixedLayout(readSrc('components/ui/TagCitation.vue'))).toBe(true)
      expect(readSrc('components/ui/ui.spec.ts')).toContain('tag-citation__node-id')
    })

    it('typographyChecklistPasses on production sources', () => {
      const detailViewSrc = readSrc('views/PaperDetailView.vue')
      expect(
        typographyChecklistPasses({
          detailViewSrc,
          detailStyleSrc: extractStyleBlocks(detailViewSrc),
          tagCitationSrc: readSrc('components/ui/TagCitation.vue'),
          papersStyleSrc: extractStyleBlocks(readSrc('views/PapersView.vue')),
          homeStyleSrc: extractStyleBlocks(readSrc('views/HomeView.vue')),
          patrolStyleSrc: extractStyleBlocks(readSrc('views/PatrolView.vue')),
          uploadStyleSrc: extractStyleBlocks(readSrc('components/papers/PaperUpload.vue')),
        }),
      ).toBe(true)
    })

    it('registers graph-qa, demo-path, and PaperDetailView spec gates', () => {
      expect(readSrc('test/graph-qa.integration.test.ts')).toContain('§1.4.4 typography acceptance checklist')
      expect(readSrc('test/demo-path.integration.test.ts')).toContain('§1.4.4 排版验收 checklist')
      expect(readSrc('views/PaperDetailView.spec.ts')).toContain('§1.4.4 typography checklist')
    })
  })

  describe('排版验收（helper 别名）', () => {
    it('问答答案区：Body-lg + pre-wrap + 内嵌灰底', () => {
      const detailViewSrc = readSrc('views/PaperDetailView.vue')
      const detailStyles = extractStyleBlocks(detailViewSrc)
      expect(answerPanelTypographyMatchesBaseline(detailViewSrc, detailStyles)).toBe(true)
    })

    it('副标题 / hint 使用 --color-text-secondary', () => {
      const papersStyles = extractStyleBlocks(readSrc('views/PapersView.vue'))
      const homeStyles = extractStyleBlocks(readSrc('views/HomeView.vue'))
      const uploadStyles = extractStyleBlocks(readSrc('components/papers/PaperUpload.vue'))
      expect(pageSubtitleUsesSecondaryColor(papersStyles, '.papers-subtitle')).toBe(true)
      expect(pageSubtitleUsesSecondaryColor(homeStyles, '.home-subtitle')).toBe(true)
      expect(uploadStyles).toMatch(/\.paper-upload__tip[\s\S]*color: var\(--color-text-secondary\)/)
    })

    it('Mono 仅 ID / code — TagCitation node_id 用 font-mono', () => {
      expect(citationTagUsesMonoNodeId(extractStyleBlocks(readSrc('components/ui/TagCitation.vue')))).toBe(true)
      const detailStyles = extractStyleBlocks(readSrc('views/PaperDetailView.vue'))
      expect(detailStyles).not.toMatch(/\.detail-qa__answer-text[\s\S]*font-family: var\(--font-mono\)/)
    })

    it('Citation 混排：label 正文 + (node_id) Mono 括号', () => {
      expect(citationTagMixedLayout(readSrc('components/ui/TagCitation.vue'))).toBe(true)
    })
  })
})
