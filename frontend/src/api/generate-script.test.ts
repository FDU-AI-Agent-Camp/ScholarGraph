import { describe, expect, it } from 'vitest'

import packageJson from '../../package.json'

describe('generate:api-types npm script', () => {
  it('is wired to openapi-typescript and repo openapi.yaml', () => {
    const script = packageJson.scripts['generate:api-types']
    expect(script).toContain('openapi-typescript')
    expect(script).toContain('../docs/api/openapi.yaml')
    expect(script).toContain('src/api/generated/schema.d.ts')
  })
})
