/**
 * 三分支联调：FE 契约 + platform fixtures + ingest 金标（develop 合入后）。
 *
 * - feature/frontend：API 客户端与 PaperStatus 类型
 * - feature/backend/platform：fixtures 种子与 HTTP 包络
 * - feature/backend/ingest：classifier_labels.csv 与语料 paper_id
 */
import { describe, expect, it } from 'vitest'

import type { PaperStatusData } from '@/api/types'
import { isFailedStatus, isTerminalStatus } from '@/utils/paperStatus'
import classifierLabelsCsv from '../../../docs/v1/eval/classifier_labels.csv?raw'
import papersListFixture from '../../../docs/api/fixtures/papers-list.json'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'
import processingFixture from '../../../docs/api/fixtures/paper-status-hss-002.json'
import ingestFailedFixture from '../../../docs/api/fixtures/paper-ingest-failed.json'

function parseClassifierLabelRows(csv: string): Array<{ paper_id: string; paradigm_gold: string }> {
  return csv
    .trim()
    .split(/\r?\n/)
    .slice(1)
    .map((line) => {
      const firstComma = line.indexOf(',')
      const secondComma = line.indexOf(',', firstComma + 1)
      return {
        paper_id: line.slice(0, firstComma),
        paradigm_gold: line.slice(firstComma + 1, secondComma),
      }
    })
}

describe('three-branch merge (FE ↔ platform fixtures ↔ ingest gold labels)', () => {
  it('classifier_labels.csv paper_ids appear in papers-list fixture', () => {
    const labels = parseClassifierLabelRows(classifierLabelsCsv)
    const listIds = new Set(papersListFixture.data.items.map((row) => row.paper_id))

    expect(labels).toHaveLength(3)
    expect(labels.map((row) => row.paradigm_gold).sort()).toEqual(['HSS', 'HSS', 'STEM'])
    for (const row of labels) {
      expect(listIds.has(row.paper_id)).toBe(true)
    }
  })

  it('platform failed status fixture matches FE failed-state narrowing', () => {
    const data = failedStatusFixture.data as PaperStatusData
    expect(isFailedStatus(data)).toBe(true)
    expect(isTerminalStatus(data.status)).toBe(true)
    expect(data.failed_during).toBe('classifying')
  })

  it('platform processing fixture has no failure fields for FE status panel', () => {
    const data = processingFixture.data as PaperStatusData
    expect(data.status).toBe('processing')
    expect(data.stage).toBe('classifying')
    expect(data.error_code).toBeUndefined()
    expect(data.failed_during).toBeUndefined()
    expect(isTerminalStatus(data.status)).toBe(false)
  })

  it('ingest API error fixture exposes INGEST_FAILED for upload failure UI', () => {
    expect(ingestFailedFixture.error.code).toBe('INGEST_FAILED')
    expect(ingestFailedFixture.error.message).toMatch(/PDF|解析|损坏/)
  })

  it('gold label STEM/HSS counts align with papers-list paradigm column', () => {
    const labels = parseClassifierLabelRows(classifierLabelsCsv)
    const stemGold = labels.filter((row) => row.paradigm_gold === 'STEM').map((row) => row.paper_id)
    const hssGold = labels.filter((row) => row.paradigm_gold === 'HSS').map((row) => row.paper_id)

    const stemList = papersListFixture.data.items.filter((row) => row.paradigm === 'STEM')
    const hssList = papersListFixture.data.items.filter((row) => row.paradigm === 'HSS')

    for (const paperId of stemGold) {
      expect(stemList.some((row) => row.paper_id === paperId)).toBe(true)
    }
    for (const paperId of hssGold) {
      expect(hssList.some((row) => row.paper_id === paperId)).toBe(true)
    }
  })
})
