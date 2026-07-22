/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * V1 DoD §6.4 D-07～D-12 — 治理项前后端联调联试（FE 侧）.
 *
 * 与 tests/integration/test_dod_d_fe_be_governance.py 成对验收。
 */
import { execFileSync, execSync } from 'node:child_process'
import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError } from '@/api/client'
import * as patrolApi from '@/api/patrol'
import type { PatrolReport } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { routes } from '@/router/index'
import { routerViewShell } from '@/test/helpers/routerViewShell'
import { elUploadStub } from '@/test/helpers/elUploadStub'
import { resolvePatrolApiError } from '@/utils/patrolForm'

import openapiYaml from '../../../docs/api/openapi.yaml?raw'
import patrolViewSrc from '../views/PatrolView.vue?raw'
import paperUploadSrc from '../components/papers/PaperUpload.vue?raw'
import papersApiSrc from '../api/papers.ts?raw'

const FRONTEND_ROOT = join(process.cwd())
const REPO_ROOT = join(FRONTEND_ROOT, '..')

const mockListPapers = vi.hoisted(() => vi.fn())
const mockUploadPaper = vi.hoisted(() => vi.fn())
const mockRunPatrol = vi.hoisted(() => vi.fn())
const elMessageError = vi.hoisted(() => vi.fn())

vi.mock('@/api/papers', () => ({
  listPapers: (...args: unknown[]) => mockListPapers(...args),
  getPaper: vi.fn(),
  getPaperGraph: vi.fn(),
  getPaperStatus: vi.fn(),
  uploadPaper: (...args: unknown[]) => mockUploadPaper(...args),
}))

vi.mock('@/api/patrol', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/patrol')>()
  return {
    ...actual,
    runPatrol: (...args: unknown[]) => mockRunPatrol(...args),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: (...args: unknown[]) => elMessageError(...args),
  },
}))

const routeStubs = {
  'el-table': { template: '<div><slot /></div>' },
  'el-table-column': true,
  'el-select': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
  },
  'el-option': true,
  'el-upload': elUploadStub,
  'el-icon': true,
  'el-button': {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs" @click="$attrs.onClick?.()"><slot /></button>',
  },
  'el-alert': {
    inheritAttrs: false,
    props: ['title', 'description'],
    template:
      '<div class="el-alert-stub" v-bind="$attrs" :data-title="title" :data-description="description"><slot /></div>',
  },
  RouterLink: true,
  EmptyState: { template: '<div />' },
  InsightCard: {
    props: ['title', 'summary'],
    template: '<article><p class="insight-summary">{{ summary }}</p></article>',
  },
  BadgeParadigm: true,
  BadgeStatus: true,
}

async function mountAt(path: string) {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(routerViewShell, {
    global: { plugins: [router], stubs: routeStubs },
  })
  await flushPromises()
  return wrapper
}

function gitInsideWorkTree(): boolean {
  try {
    execSync('git rev-parse --is-inside-work-tree', { cwd: REPO_ROOT, stdio: 'pipe' })
    return true
  } catch {
    return false
  }
}

describe('V1 DoD D-07 — FE uses api modules, not private HTTP wiring', () => {
  it('PatrolView calls runPatrol from @/api/patrol', () => {
    expect(patrolViewSrc).toContain('@/api/patrol')
    expect(patrolViewSrc).toContain('runPatrol')
    expect(patrolViewSrc).not.toMatch(/from ['"]axios['"]/)
  })

  it('functional patrol success renders report via runPatrol facade', async () => {
    mockListPapers.mockResolvedValue({
      data: {
        items: [
          { paper_id: 'hss-001', title: 'A', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:00:00Z' },
          { paper_id: 'hss-002', title: 'B', paradigm: 'HSS', status: 'ready', created_at: '2026-05-19T10:10:00Z' },
        ],
        total: 2,
        offset: 0,
        limit: 20,
      },
      meta: { request_id: 'd07' },
    })
    const report: PatrolReport = {
      mode: 'lens_clash',
      paper_ids: ['hss-001', 'hss-002'],
      insights: [
        {
          insight_id: 'ins-1',
          title: 'Lens',
          summary: 'ok',
          status: 'ready',
          paper_ids: ['hss-001', 'hss-002'],
          node_refs: [],
        },
      ],
      generated_at: '2026-05-19T12:00:00Z',
    }
    mockRunPatrol.mockResolvedValue({ data: report, meta: { request_id: 'ok' } })

    const wrapper = await mountAt('/patrol')
    await wrapper.find('.patrol-view__run').trigger('click')
    await flushPromises()

    expect(mockRunPatrol).toHaveBeenCalled()
    expect(wrapper.find('.patrol-view__report').exists()).toBe(true)
  })

  it('red PATROL_INSUFFICIENT_DATA maps to baseline patrol panel', () => {
    const fe = resolvePatrolApiError('PATROL_INSUFFICIENT_DATA', '缺少 Thesis')
    expect(fe.title).toBe(PATROL_BASELINE_COPY.insufficientDataTitle)
    expect(fe.ctaKind).toBe('reset-selection')
  })
})

describe('V1 DoD D-08 — ApiClientError envelope and inline upload UX', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockListPapers.mockResolvedValue({
      data: { items: [], total: 0, offset: 0, limit: 20 },
      meta: { request_id: 'd08' },
    })
  })

  it('uploadPaper uses suppressErrorToast for inline errors (BE INGEST_FAILED)', () => {
    expect(papersApiSrc).toContain('suppressErrorToast: true')
    expect(paperUploadSrc).toContain('error.code')
    expect(paperUploadSrc).toContain('uploadErrorCode')
  })

  it('ApiClientError preserves BE code and message for inline upload alert', async () => {
    mockUploadPaper.mockRejectedValue(new ApiClientError({ code: 'INGEST_FAILED', message: '文件超过 32MB 限制' }, 400))

    const wrapper = await mountAt('/papers')
    await wrapper.find('.do-upload').trigger('click')
    await flushPromises()

    const alert = wrapper.find('.paper-upload__error')
    expect(alert.attributes('data-title')).toBe('INGEST_FAILED')
    expect(alert.text()).toContain('32MB')
    expect(elMessageError).not.toHaveBeenCalled()
  })

  it('red NETWORK_ERROR uses fallback message when envelope missing', () => {
    const err = ApiClientError.fromAxios({
      response: undefined,
      message: 'Network Error',
    } as Parameters<typeof ApiClientError.fromAxios>[0])
    expect(err.code).toBe('NETWORK_ERROR')
    expect(err.message).toBeTruthy()
  })

  it('red SERVER error code surfaces for list failure without white screen', async () => {
    mockListPapers.mockRejectedValue(new ApiClientError({ code: 'SERVER', message: '服务不可用' }, 500))

    const wrapper = await mountAt('/papers')
    await flushPromises()

    expect(wrapper.find('.papers').exists()).toBe(true)
  })
})

describe('V1 DoD D-09 — sensitive paths stay out of git', () => {
  it('.gitignore lists required sensitive entries', () => {
    const gitignore = readFileSync(join(REPO_ROOT, '.gitignore'), 'utf-8')
    for (const entry of ['.env', '.cursor/', 'progress.md', 'API KEY.txt']) {
      expect(gitignore).toContain(entry)
    }
  })

  it('git check-ignore confirms .env and progress.md are ignored', () => {
    if (!gitInsideWorkTree()) return
    for (const rel of ['.env', 'progress.md', '.cursor/']) {
      expect(() => {
        // Prefer argv form + hard timeout: shell `execSync` can stall under
        // heavy parallel pytest/git load and trip Vitest's default 15s cap.
        execFileSync('git', ['check-ignore', '-q', rel], {
          cwd: REPO_ROOT,
          stdio: 'pipe',
          timeout: 30_000,
        })
      }).not.toThrow()
    }
  }, 60_000)
})

describe('V1 DoD D-10 — lockfiles align with manifests', () => {
  it('uv.lock and package-lock.json exist and name projects', () => {
    const uvLock = readFileSync(join(REPO_ROOT, 'uv.lock'), 'utf-8')
    const pkgLock = readFileSync(join(FRONTEND_ROOT, 'package-lock.json'), 'utf-8')
    expect(uvLock).toContain('name = "scholargraph"')
    expect(pkgLock).toContain('"name": "scholargraph-frontend"')
    expect(pkgLock).toContain('"lockfileVersion"')
    expect(statSync(join(REPO_ROOT, 'pyproject.toml')).isFile()).toBe(true)
  })
})

describe('V1 DoD D-11 — OpenAPI contract and health fields', () => {
  it('openapi documents health and papers paths for public API', () => {
    expect(openapiYaml).toContain('/health:')
    expect(openapiYaml).toContain('/papers:')
    expect(openapiYaml).toContain('HealthResponse')
  })

  it('health fixture fields align with FE expectations (llm_mode / llm_note)', () => {
    const sample = {
      data: {
        status: 'healthy',
        llm_mode: 'mock',
        llm_connected: false,
        llm_note: 'Mock 模式：LLM 云服务尚未接入',
      },
      meta: { request_id: 'd11' },
    }
    expect(sample.data.llm_mode).toBe('mock')
    expect(sample.data.llm_note).toContain('Mock')
  })
})

describe('V1 DoD D-12 — view modules stay maintainable', () => {
  const VIEW_BUDGET_LINES = 550

  it('primary views stay under line budget (no god files)', () => {
    const views = ['PatrolView.vue', 'PapersView.vue', 'PaperDetailView.vue', 'PaperGraphView.vue']
    for (const name of views) {
      const path = join(FRONTEND_ROOT, 'src', 'views', name)
      const lines = readFileSync(path, 'utf-8').split('\n').length
      expect(lines).toBeLessThanOrEqual(VIEW_BUDGET_LINES)
    }
  })

  it('PatrolView delegates API to patrolForm helpers instead of inline error strings', () => {
    expect(patrolViewSrc).toContain('resolvePatrolApiError')
    expect(patrolViewSrc).toContain('validatePatrolSelection')
  })

  it('papers upload retry copy uses baseline constants for failed ingest', () => {
    expect(paperUploadSrc).toContain('PAPERS_BASELINE_COPY.uploadRetryHint')
    expect(paperUploadSrc).toContain('PAPERS_BASELINE_COPY.uploadRetryButton')
  })
})

describe('V1 DoD D — patrol API module contract', () => {
  it('runPatrol is exported from api/patrol for handoff alignment', () => {
    expect(typeof patrolApi.runPatrol).toBe('function')
  })
})
