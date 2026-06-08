/**
 * V1 DoD §6.4 D-01～D-12 — 代码基座规范性（静态契约 + CI 对齐）。
 *
 * 与 tests/test_dod_d_standards.py、scripts/run_d_gates.py 成对验收。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

import packageJson from '../../package.json'
import tsconfig from '../../tsconfig.json'
import backendWorkflow from '../../../.github/workflows/backend.yml?raw'
import frontendWorkflow from '../../../.github/workflows/frontend.yml?raw'
import eslintConfigSource from '../../eslint.config.js?raw'
import agentsMd from '../../../AGENTS.md?raw'
import workAssignment from '../../../docs/v1/work-assignment.md?raw'
import handoffDoc from '../../../docs/v1/handoff-to-platform.md?raw'
import gitignoreSource from '../../../.gitignore?raw'

const FRONTEND_ROOT = join(process.cwd())
const REPO_ROOT = join(FRONTEND_ROOT, '..')

function listSourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const stat = statSync(full)
    if (stat.isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') continue
      listSourceFiles(full, acc)
      continue
    }
    if (/\.(ts|vue)$/.test(entry)) acc.push(full)
  }
  return acc
}

const CONVENTIONAL_TYPES = [
  'feat',
  'fix',
  'docs',
  'style',
  'refactor',
  'perf',
  'test',
  'build',
  'ci',
  'chore',
  'revert',
] as const

const CONVENTIONAL_HEADER = /^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9./_-]+\))?!?: .+/i

const FEATURE_BRANCH = /^feature\/(frontend\/[a-z0-9._-]+|backend\/[a-z0-9._-]+(?:\/[a-z0-9._-]+)?)$/i

describe('V1 DoD D-03 — vue-tsc strict', () => {
  it('tsconfig enables strict compiler options', () => {
    const opts = tsconfig.compilerOptions
    expect(opts.strict).toBe(true)
    expect(opts.noUnusedLocals).toBe(true)
    expect(opts.noUnusedParameters).toBe(true)
    expect(opts.noFallthroughCasesInSwitch).toBe(true)
  })

  it('package.json exposes typecheck script for vue-tsc', () => {
    expect(packageJson.scripts.typecheck).toBe('vue-tsc --noEmit')
    expect(packageJson.scripts.build).toContain('vue-tsc')
  })
})

describe('V1 DoD D-04 — ESLint + Prettier + Knip', () => {
  it('check script chains typecheck, format:check, lint, knip', () => {
    const check = packageJson.scripts.check
    expect(check).toContain('typecheck')
    expect(check).toContain('format:check')
    expect(check).toContain('lint')
    expect(check).toContain('knip')
  })

  it('eslint blocks raw axios outside src/api (D-08 synergy)', () => {
    expect(eslintConfigSource).toContain('no-restricted-imports')
    expect(eslintConfigSource).toContain('axios')
  })

  it('eslint uses Vue recommended + Prettier compatibility', () => {
    expect(eslintConfigSource).toContain('flat/recommended')
    expect(eslintConfigSource).toContain('eslintConfigPrettier')
  })
})

describe('V1 DoD D-01/D-02 — backend CI gate wiring', () => {
  it('backend workflow runs ruff check/format and pytest not red', () => {
    expect(backendWorkflow).toContain('uv run ruff check backend tests scripts')
    expect(backendWorkflow).toContain('uv run ruff format --check backend tests scripts')
    expect(backendWorkflow).toContain('pytest -q -m "not red and not live_mineru and not live_grobid"')
  })
})

describe('V1 DoD D-03/D-04 — frontend CI gate wiring', () => {
  it('frontend workflow runs check, test, and build', () => {
    expect(frontendWorkflow).toContain('npm run check')
    expect(frontendWorkflow).toContain('npm run test')
    expect(frontendWorkflow).toContain('npm run build')
    expect(frontendWorkflow).toContain('working-directory: frontend')
  })

  it('check:ci extends check with test and build', () => {
    expect(packageJson.scripts['check:ci']).toContain('npm run check')
    expect(packageJson.scripts['check:ci']).toContain('npm run test')
    expect(packageJson.scripts['check:ci']).toContain('npm run build')
  })
})

describe('V1 DoD D-05 — Conventional Commits documented', () => {
  it('AGENTS.md lists allowed commit types', () => {
    for (const commitType of CONVENTIONAL_TYPES) {
      expect(agentsMd).toContain(`\`${commitType}\``)
    }
  })

  it('validates sample commit headers against regex', () => {
    const samples = [
      'feat(qa): wire SSE to qa_stream',
      'test(integration): E robustness FE↔BE',
      'docs(README): 完善协作说明',
    ]
    for (const subject of samples) {
      expect(CONVENTIONAL_HEADER.test(subject)).toBe(true)
    }
    expect(CONVENTIONAL_HEADER.test('update stuff')).toBe(false)
  })
})

describe('V1 DoD D-06 — feature branch naming', () => {
  it('work-assignment documents feature/frontend and feature/backend patterns', () => {
    expect(workAssignment).toContain('feature/frontend/{简述}')
    expect(workAssignment).toContain('feature/backend/{工作类型}/{简述}')
    expect(workAssignment).toContain('禁止')
    expect(workAssignment).toContain('feature/be1/')
  })

  it('accepts documented branch name examples', () => {
    const ok = [
      'feature/frontend/scaffold-mock',
      'feature/backend/graph-qa/multiscale-qa',
      'feature/backend/be3-graph-qa-complete',
    ]
    for (const branch of ok) {
      expect(FEATURE_BRANCH.test(branch)).toBe(true)
    }
    expect(FEATURE_BRANCH.test('feature/be1/ingest')).toBe(false)
  })
})

describe('V1 DoD D-07 — BE handoff doc (no private routes in delivery modules)', () => {
  it('handoff-to-platform forbids BE-1～4 from registering HTTP routes', () => {
    expect(handoffDoc).toContain('不要')
    expect(handoffDoc).toContain('HTTP 路由')
    expect(handoffDoc).toContain('只交付 Service')
  })
})

describe('V1 DoD D-08 — no raw axios outside src/api', () => {
  it('eslint restricts axios to src/api/**/*.ts', () => {
    expect(eslintConfigSource).toContain("files: ['src/api/**/*.ts']")
  })

  it('source scan finds no axios imports outside src/api', () => {
    const srcRoot = join(FRONTEND_ROOT, 'src')
    const axiosImport = /from ['"]axios['"]|require\(['"]axios['"]\)/
    const offenders: string[] = []
    for (const file of listSourceFiles(srcRoot)) {
      const rel = relative(srcRoot, file).replace(/\\/g, '/')
      if (rel.startsWith('api/')) continue
      const text = readFileSync(file, 'utf-8')
      if (axiosImport.test(text)) offenders.push(rel)
    }
    expect(offenders).toEqual([])
  })
})

describe('V1 DoD D-09 — sensitive paths gitignored', () => {
  it('.gitignore blocks .env, .cursor/, progress.md, and API KEY.txt', () => {
    for (const entry of ['.env', '.cursor/', 'progress.md', 'API KEY.txt']) {
      expect(gitignoreSource).toContain(entry)
    }
  })
})

describe('V1 DoD D-10 — lockfiles committed with manifests', () => {
  it('uv.lock and package-lock.json exist at repo root paths', () => {
    expect(statSync(join(REPO_ROOT, 'pyproject.toml')).isFile()).toBe(true)
    expect(statSync(join(REPO_ROOT, 'uv.lock')).isFile()).toBe(true)
    expect(statSync(join(FRONTEND_ROOT, 'package.json')).isFile()).toBe(true)
    expect(statSync(join(FRONTEND_ROOT, 'package-lock.json')).isFile()).toBe(true)
  })
})

describe('V1 DoD D-11/D-12 — review sampling (continuous)', () => {
  it('AGENTS.md documents SRP and function length guidance for D-12 reviews', () => {
    expect(agentsMd).toContain('职责单一')
    expect(agentsMd).toContain('上帝类')
  })

  it('openapi.yaml remains the public API contract reference for D-11 reviews', () => {
    expect(readFileSync(join(REPO_ROOT, 'docs/api/openapi.yaml'), 'utf-8')).toContain('/papers')
  })
})
