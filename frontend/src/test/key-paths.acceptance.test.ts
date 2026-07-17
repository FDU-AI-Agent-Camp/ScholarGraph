/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * §14.6 关键路径速查 — 仓库结构与门禁脚本（不替代 npm run typecheck/lint/build）。
 */
import { describe, expect, it, vi } from 'vitest'

import packageJson from '../../package.json'
import tsconfig from '../../tsconfig.json'
import * as client from '@/api/client'
import * as papersApi from '@/api/papers'
import type { PaperStatusData } from '@/api/types'
import { usePaperStatus } from '@/composables/usePaperStatus'
import openapiYaml from '../../../docs/api/openapi.yaml?raw'
import frontendWorkflow from '../../../.github/workflows/frontend.yml?raw'
import eslintConfigSource from '../../eslint.config.js?raw'
import failedStatusFixture from '../../../docs/api/fixtures/paper-status-hss-failed-001.json'

describe('§14.6 key paths (frontend TS hardening)', () => {
  it('keeps tsconfig strict compiler options enabled', () => {
    const opts = tsconfig.compilerOptions
    expect(opts.strict).toBe(true)
    expect(opts.noUnusedLocals).toBe(true)
    expect(opts.noUnusedParameters).toBe(true)
    expect(opts.noFallthroughCasesInSwitch).toBe(true)
  })

  it('documents stage-acceptance npm scripts in package.json', () => {
    expect(packageJson.scripts.typecheck).toBe('vue-tsc --noEmit')
    expect(packageJson.scripts.lint).toBe('eslint .')
    expect(packageJson.scripts['format:check']).toBe('prettier --check .')
    expect(packageJson.scripts.knip).toBe('knip')
    expect(packageJson.scripts.check).toContain('typecheck')
    expect(packageJson.scripts.check).toContain('format:check')
    expect(packageJson.scripts.check).toContain('lint')
    expect(packageJson.scripts.check).toContain('knip')
    expect(packageJson.scripts['check:ci']).toContain('npm run check')
    expect(packageJson.scripts.build).toContain('vue-tsc')
    expect(packageJson.scripts.build).toContain('vite build')
    expect(packageJson.scripts.test).toBe('vitest run')
    expect(packageJson.scripts['demo:setup']).toContain('run_frontend_demo.py')
  })

  it('openapi PaperStatusData includes failed-state fields', () => {
    expect(openapiYaml).toMatch(/PaperStatusData:/)
    expect(openapiYaml).toMatch(/error_code:/)
    expect(openapiYaml).toMatch(/failed_during:/)
  })

  it('types.ts PaperStatusData aligns with failed fixture', () => {
    const data = failedStatusFixture.data as PaperStatusData
    expect(data.status).toBe('failed')
    expect(data.error_code).toBe('LLM_JSON_INVALID')
    expect(data.failed_during).toBe('classifying')
  })

  it('client exposes typed envelope helpers without exporting raw http', () => {
    expect(typeof client.getData).toBe('function')
    expect(typeof client.postData).toBe('function')
    expect(typeof client.getApiV1Root).toBe('function')
    expect(client.ApiClientError.name).toBe('ApiClientError')
    expect('http' in client).toBe(false)
  })

  it('papers status API uses getData on /papers/{id}/status', async () => {
    const getDataSpy = vi
      .spyOn(client, 'getData')
      .mockResolvedValue(failedStatusFixture as { data: PaperStatusData; meta: { request_id: string } })
    const res = await papersApi.getPaperStatus('hss-failed-001')
    expect(getDataSpy).toHaveBeenCalledWith('/papers/hss-failed-001/status')
    expect(res.data.error_code).toBe('LLM_JSON_INVALID')
    getDataSpy.mockRestore()
  })

  it('usePaperStatus composable is exported for PaperStatusPanel wiring', () => {
    expect(typeof usePaperStatus).toBe('function')
    expect(usePaperStatus.name).toBe('usePaperStatus')
  })

  it('CI workflow runs npm ci gate steps for frontend', () => {
    expect(frontendWorkflow).toContain('npm ci')
    expect(frontendWorkflow).toContain('npm run check')
    expect(frontendWorkflow).toContain('npm run test')
    expect(frontendWorkflow).toContain('npm run build')
    expect(frontendWorkflow).toContain('working-directory: frontend')
  })

  it('eslint blocks raw axios outside src/api', () => {
    expect(eslintConfigSource).toContain('no-restricted-imports')
    expect(eslintConfigSource).toContain('axios')
    expect(eslintConfigSource).toContain("files: ['src/api/**/*.ts']")
  })

  it('eslint uses Vue recommended preset and Prettier compatibility', () => {
    expect(eslintConfigSource).toContain('flat/recommended')
    expect(eslintConfigSource).toContain('eslintConfigPrettier')
  })
})
