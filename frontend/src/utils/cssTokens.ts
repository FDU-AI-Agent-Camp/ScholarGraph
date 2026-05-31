/** Read a CSS custom property from :root; fall back when SSR/tests omit tokens. */
export function cssToken(name: string, fallback: string): string {
  if (typeof document === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}
