import { extractStyleBlocks } from '@/test/helpers/motionDiscipline'

/** ui-design-progress §1.4.4 forbidden marketing / placeholder copy. */
export const FORBIDDEN_MARKETING_WORDS = [
  '卓越',
  '赋能',
  '一站式',
  '一体化解决方案',
  '极致',
  '无缝',
  '助力',
  '打造',
  'Lorem',
  'TODO 文案',
] as const

export const FORBIDDEN_EMPTY_PLACEHOLDERS = [
  '请输入内容',
  '请输入…',
  '请输入问题',
  '请输入您的',
  'placeholder="请输入"',
] as const

export const FORBIDDEN_PASSIVE_UPLOAD_PATTERNS = ['在此上传您的文档', '解构功能可通过上传触发', '功能可通过'] as const

/** Page subtitles / hints that must stay secondary color (§1.4.4 排版验收). */
export const TYPOGRAPHY_SECONDARY_SUBTITLE_SELECTORS = [
  { relativePath: 'views/PapersView.vue', selector: '.papers-subtitle' },
  { relativePath: 'views/HomeView.vue', selector: '.home-subtitle' },
  { relativePath: 'views/PatrolView.vue', selector: '.patrol-view__subtitle' },
] as const

/** Body copy selectors that must not be forced into mono (§1.4.4 排版验收). */
export const TYPOGRAPHY_BODY_NO_MONO_SELECTORS = [
  '.detail-qa__answer-text',
  '.empty-state__body',
  '.tag-citation__label',
] as const

export function containsForbiddenMarketingWord(src: string): string | null {
  for (const word of FORBIDDEN_MARKETING_WORDS) {
    if (src.includes(word)) {
      return word
    }
  }
  return null
}

export function containsForbiddenEmptyPlaceholder(src: string): string | null {
  for (const phrase of FORBIDDEN_EMPTY_PLACEHOLDERS) {
    if (src.includes(phrase)) {
      return phrase
    }
  }
  return null
}

export function answerPanelTypographyMatchesBaseline(detailViewSrc: string, detailStyleSrc: string): boolean {
  const answerPanelBlock = detailStyleSrc.match(/\.detail-qa__answer-panel\s*\{[^}]*\}/)?.[0] ?? ''
  return (
    detailViewSrc.includes('class="detail-qa__answer-panel text-body-lg"') &&
    detailViewSrc.includes('class="detail-qa__answer-text"') &&
    answerPanelBlock.includes('white-space: pre-wrap') &&
    answerPanelBlock.includes('var(--color-bg-subtle)')
  )
}

export function citationTagUsesMonoNodeId(tagCitationStyleSrc: string): boolean {
  return tagCitationStyleSrc.includes('tag-citation__node-id') && tagCitationStyleSrc.includes('var(--font-mono)')
}

export function pageSubtitleUsesSecondaryColor(styleSrc: string, selector: string): boolean {
  const escaped = selector.replace('.', '\\.')
  const block = styleSrc.match(new RegExp(`${escaped}\\s*\\{[^}]*\\}`))?.[0] ?? ''
  return block.includes('color: var(--color-text-secondary)')
}

export function citationTagMixedLayout(tagCitationSrc: string): boolean {
  const template = tagCitationSrc.match(/<template>([\s\S]*?)<\/template>/)?.[1] ?? ''
  const styles = extractStyleBlocks(tagCitationSrc)

  return (
    template.includes('class="tag-citation__label"') &&
    template.includes('class="tag-citation__node-id"') &&
    /\(\{\{\s*nodeId\s*\}\}\)/.test(template) &&
    citationTagUsesMonoNodeId(styles) &&
    !/\.tag-citation__label[\s\S]*font-family: var\(--font-mono\)/.test(styles)
  )
}

export function bodySelectorAvoidsMono(styleSrc: string, selector: string): boolean {
  const escaped = selector.replace('.', '\\.')
  const block = styleSrc.match(new RegExp(`${escaped}\\s*\\{[^}]*\\}`))?.[0] ?? ''
  if (block.length === 0) {
    return true
  }
  return !/font-family:\s*var\(--font-mono\)/.test(block)
}

export function allBodySelectorsAvoidMono(styleSrc: string): boolean {
  return TYPOGRAPHY_BODY_NO_MONO_SELECTORS.every((selector) => bodySelectorAvoidsMono(styleSrc, selector))
}

export function allRegisteredSubtitlesUseSecondary(readStyle: (relativePath: string) => string): boolean {
  return TYPOGRAPHY_SECONDARY_SUBTITLE_SELECTORS.every(({ relativePath, selector }) =>
    pageSubtitleUsesSecondaryColor(readStyle(relativePath), selector),
  )
}

/** Aggregated §1.4.4 typography checklist for integration gates. */
export function typographyChecklistPasses(options: {
  detailViewSrc: string
  detailStyleSrc: string
  tagCitationSrc: string
  papersStyleSrc: string
  homeStyleSrc: string
  patrolStyleSrc: string
  uploadStyleSrc: string
}): boolean {
  return (
    answerPanelTypographyMatchesBaseline(options.detailViewSrc, options.detailStyleSrc) &&
    pageSubtitleUsesSecondaryColor(options.papersStyleSrc, '.papers-subtitle') &&
    pageSubtitleUsesSecondaryColor(options.homeStyleSrc, '.home-subtitle') &&
    pageSubtitleUsesSecondaryColor(options.patrolStyleSrc, '.patrol-view__subtitle') &&
    /\.paper-upload__tip[\s\S]*color: var\(--color-text-secondary\)/.test(options.uploadStyleSrc) &&
    citationTagMixedLayout(options.tagCitationSrc) &&
    allBodySelectorsAvoidMono(options.detailStyleSrc) &&
    allBodySelectorsAvoidMono(extractStyleBlocks(options.tagCitationSrc)) &&
    allBodySelectorsAvoidMono(extractStyleBlocks('components/ui/EmptyState.vue'))
  )
}
