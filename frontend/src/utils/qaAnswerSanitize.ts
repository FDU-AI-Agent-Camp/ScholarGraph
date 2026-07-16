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
  return sanitizeChunk(delta)
}
