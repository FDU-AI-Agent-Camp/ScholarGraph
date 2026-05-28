import { describe, expect, it } from 'vitest'

import * as mocks from '@/mocks'
import papersListFixture from '../../../docs/api/fixtures/papers-list.json'

describe('src/mocks re-exports', () => {
  it('papersList matches canonical docs/api fixture', () => {
    expect(mocks.papersList).toEqual(papersListFixture)
  })

  it('exports failed status fixture with error_code', () => {
    expect(mocks.paperStatusFailed.data.error_code).toBe('LLM_JSON_INVALID')
  })
})
