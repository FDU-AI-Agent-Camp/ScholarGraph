import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND_SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

/** Parse hex/color token declarations from the primary :root block in tokens.css. */
export function loadDesignTokenMap(): Record<string, string> {
  const css = readFileSync(resolve(FRONTEND_SRC, 'styles/tokens.css'), 'utf8')
  const rootBlock = css.match(/:root\s*\{([\s\S]*?)\}/)?.[1] ?? ''
  const tokens: Record<string, string> = {}

  for (const match of rootBlock.matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    const name = match[1]
    const raw = match[2]?.trim()
    if (!name || !raw) {
      continue
    }
    tokens[name] = raw.toLowerCase()
  }

  return tokens
}

export function readFrontendSource(relativePathFromSrc: string): string {
  return readFileSync(resolve(FRONTEND_SRC, relativePathFromSrc), 'utf8')
}

/** design-spec §5 / §1.4.1 semantic colors used by Phase 2 badges. */
export const DESIGN_SPEC_SEMANTIC_COLORS = {
  hssBg: '#fef3c7',
  hssText: '#92400e',
  stemBg: '#dbeafe',
  stemText: '#1e40af',
  success: '#059669',
  warning: '#d97706',
  error: '#dc2626',
  info: '#2563eb',
  textMuted: '#9ca3af',
  citationActive: '#e11d48',
  citationActiveText: '#be123c',
  citationActiveBg: '#fff1f2',
} as const
