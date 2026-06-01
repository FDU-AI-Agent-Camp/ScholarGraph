/** Augment vue-router RouteMeta (see module declaration below). */
export interface AppRouteMeta {
  /** Page title for document / header. */
  title: string
  /** Show in primary navigation when true. */
  nav?: boolean
  /** Graph canvas routes: no page-card, main area full-bleed. */
  fullBleed?: boolean
}

declare module 'vue-router' {
  // Merge app meta fields into vue-router RouteMeta.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type -- module augmentation
  interface RouteMeta extends AppRouteMeta {}
}

export const RouteName = {
  Home: 'home',
  Papers: 'papers',
  PaperDetail: 'paper-detail',
  PaperGraph: 'paper-graph',
  Patrol: 'patrol',
} as const

export type AppRouteName = (typeof RouteName)[keyof typeof RouteName]
