/** WCAG 2.x contrast helpers for §1.4.1 acceptance tests. */

const MIN_CHANNEL = 0
const MAX_CHANNEL = 255

export function parseHexColor(hex: string): { r: number; g: number; b: number } {
  const normalized = hex.replace('#', '').toLowerCase()
  const expanded =
    normalized.length === 3
      ? normalized
          .split('')
          .map((channel) => channel + channel)
          .join('')
      : normalized

  return {
    r: Number.parseInt(expanded.slice(0, 2), 16),
    g: Number.parseInt(expanded.slice(2, 4), 16),
    b: Number.parseInt(expanded.slice(4, 6), 16),
  }
}

function channelToLinear(channel: number): number {
  const normalized = channel / MAX_CHANNEL
  if (normalized <= 0.03928) {
    return normalized / 12.92
  }
  return ((normalized + 0.055) / 1.055) ** 2.4
}

export function relativeLuminance(hex: string): number {
  const { r, g, b } = parseHexColor(hex)
  const red = channelToLinear(Math.max(MIN_CHANNEL, Math.min(MAX_CHANNEL, r)))
  const green = channelToLinear(Math.max(MIN_CHANNEL, Math.min(MAX_CHANNEL, g)))
  const blue = channelToLinear(Math.max(MIN_CHANNEL, Math.min(MAX_CHANNEL, b)))
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

export function contrastRatio(foregroundHex: string, backgroundHex: string): number {
  const foreground = relativeLuminance(foregroundHex)
  const background = relativeLuminance(backgroundHex)
  const lighter = Math.max(foreground, background)
  const darker = Math.min(foreground, background)
  return (lighter + 0.05) / (darker + 0.05)
}

export const WCAG_AA_TEXT_CONTRAST = 4.5
export const WCAG_AA_UI_CONTRAST = 3
