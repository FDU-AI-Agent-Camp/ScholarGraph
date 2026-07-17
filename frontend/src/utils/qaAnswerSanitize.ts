/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Lightweight client-side fallback for QA answer Markdown artifacts.
 * Backend is the source of truth; this guards historical or bypassed payloads.
 */

const EMPTY_BACKTICK_PAIR_RE = /`[ \t]*`/g
const INLINE_CODE_RE = /`([^`]*?)`/g
const BOLD_RE = /\*\*([^*]+?)\*\*/g
const HEADER_RE = /^#{1,6}\s+/gm
const EXCESS_BACKTICKS_RE = /`{3,}/g
const ORPHAN_BACKTICK_RUN_RE = /[ \t]*`+[ \t]*/g
const MULTI_SPACE_RE = / {2,}/g
const SPACE_BEFORE_CJK_PUNCT_RE = / +([。，、；：！？""''（）【】《》…])/g
const CJK_PUNCT_START_RE = /^[。，、；：！？""''（）【】《》…]/

function sanitizeChunk(text: string): string {
  if (!text) {
    return text
  }
  return text
    .replace(EMPTY_BACKTICK_PAIR_RE, '')
    .replace(INLINE_CODE_RE, (_match, inner: string) => inner)
    .replace(BOLD_RE, '$1')
    .replace(HEADER_RE, '')
    .replace(EXCESS_BACKTICKS_RE, '')
}

function polishStreamRelease(text: string, pendingTrailingSpace: { value: string }, flush = false): string {
  if (pendingTrailingSpace.value) {
    if (text && CJK_PUNCT_START_RE.test(text)) {
      pendingTrailingSpace.value = ''
    } else if (text) {
      text = `${pendingTrailingSpace.value}${text}`
      pendingTrailingSpace.value = ''
    } else if (flush) {
      text = pendingTrailingSpace.value
      pendingTrailingSpace.value = ''
    }
  }

  if (!text) {
    return ''
  }

  text = text.replace(SPACE_BEFORE_CJK_PUNCT_RE, '$1')

  if (flush) {
    return text
  }

  const strippedLen = text.replace(/[ \t]+$/, '').length
  if (strippedLen < text.length) {
    pendingTrailingSpace.value = text.slice(strippedLen)
    text = text.slice(0, strippedLen)
  }
  return text
}

/** Stateful sanitizer for streaming QA deltas on the client. */
export class QaAnswerDeltaSanitizer {
  private pendingTrailingSpace = { value: '' }

  feed(delta: string): string {
    return polishStreamRelease(sanitizeChunk(delta), this.pendingTrailingSpace)
  }

  flush(): string {
    return polishStreamRelease('', this.pendingTrailingSpace, true)
  }
}

/** Final pass over a complete answer string. */
export function sanitizeQaAnswer(text: string): string {
  if (!text) {
    return text
  }
  return sanitizeChunk(text)
    .replace(/`/g, '')
    .replace(/\*\*/g, '')
    .replace(ORPHAN_BACKTICK_RUN_RE, ' ')
    .replace(MULTI_SPACE_RE, ' ')
    .replace(SPACE_BEFORE_CJK_PUNCT_RE, '$1')
}

/** Sanitize one streaming delta before appending to the answer buffer. */
export function sanitizeQaAnswerDelta(delta: string): string {
  return sanitizeChunk(delta).replace(SPACE_BEFORE_CJK_PUNCT_RE, '$1')
}
