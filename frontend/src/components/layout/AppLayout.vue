<script setup lang="ts">
import { Close, Document, HomeFilled, Menu, Search } from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { MOBILE_NAV_MAX_WIDTH_PX, SHELL_BASELINE_COPY } from '@/constants/shellCopy'
import { RouteName } from '@/router/meta'

const route = useRoute()
const router = useRouter()

const mobileNavOpen = ref(false)
const isMobileViewport = ref(false)
let mobileMediaQuery: MediaQueryList | null = null

const activeNav = computed(() => {
  if (route.path.startsWith('/papers')) {
    return '/papers'
  }
  if (route.path.startsWith('/patrol')) {
    return '/patrol'
  }
  return route.path
})

const pageTitle = computed(() => route.meta.title ?? 'ScholarGraph')
const isFullBleed = computed(() => route.meta.fullBleed === true)

const contentShellClass = computed(() => (isFullBleed.value ? 'shell-content shell-content--full-bleed' : 'page-card'))

interface ShellBreadcrumb {
  label: string
  to?: string
}

const breadcrumbs = computed((): ShellBreadcrumb[] => {
  const paperId = typeof route.params.paperId === 'string' ? route.params.paperId : ''

  if (route.name === RouteName.PaperGraph && paperId) {
    return [{ label: '文献库', to: '/papers' }, { label: '论文详情', to: `/papers/${paperId}` }, { label: '知识图谱' }]
  }

  if (route.name === RouteName.PaperDetail && paperId) {
    return [{ label: '文献库', to: '/papers' }, { label: '论文详情' }]
  }

  return []
})

function syncMobileViewport(matches: boolean): void {
  isMobileViewport.value = matches
  if (!matches) {
    mobileNavOpen.value = false
  }
}

function onMobileViewportChange(event: MediaQueryListEvent): void {
  syncMobileViewport(event.matches)
}

onMounted(() => {
  mobileMediaQuery = window.matchMedia(`(max-width: ${MOBILE_NAV_MAX_WIDTH_PX}px)`)
  syncMobileViewport(mobileMediaQuery.matches)
  mobileMediaQuery.addEventListener('change', onMobileViewportChange)
})

onUnmounted(() => {
  mobileMediaQuery?.removeEventListener('change', onMobileViewportChange)
})

watch(
  () => route.path,
  () => {
    mobileNavOpen.value = false
  },
)

function toggleMobileNav(): void {
  mobileNavOpen.value = !mobileNavOpen.value
}

function closeMobileNav(): void {
  mobileNavOpen.value = false
}

function handleNavSelect(index: string): void {
  closeMobileNav()
  void router.push(index)
}
</script>

<template>
  <el-container class="layout" :class="{ 'layout--mobile-nav-open': mobileNavOpen && isMobileViewport }">
    <div v-if="mobileNavOpen && isMobileViewport" class="aside-backdrop" aria-hidden="true" @click="closeMobileNav" />
    <el-aside width="240px" :class="['aside', { 'aside--open': mobileNavOpen }]">
      <router-link class="brand" to="/" @click="closeMobileNav">
        <strong class="brand-name">ScholarGraph</strong>
        <span class="tag">V1</span>
      </router-link>
      <el-menu :default-active="activeNav" class="menu" @select="handleNavSelect">
        <el-menu-item index="/">
          <el-icon class="nav-icon"><HomeFilled /></el-icon>
          <span class="nav-label">工作台</span>
        </el-menu-item>
        <el-menu-item index="/papers">
          <el-icon class="nav-icon"><Document /></el-icon>
          <span class="nav-label">文献库</span>
        </el-menu-item>
        <el-menu-item index="/patrol">
          <el-icon class="nav-icon"><Search /></el-icon>
          <span class="nav-label">共同体巡检</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container class="main-column">
      <el-header class="header">
        <div class="header-start">
          <button
            v-if="isMobileViewport"
            type="button"
            class="header-menu-toggle"
            :aria-label="
              mobileNavOpen ? SHELL_BASELINE_COPY.mobileNavCloseLabel : SHELL_BASELINE_COPY.mobileNavToggleLabel
            "
            :aria-expanded="mobileNavOpen ? 'true' : 'false'"
            @click="toggleMobileNav"
          >
            <el-icon class="header-menu-toggle__icon">
              <Close v-if="mobileNavOpen" />
              <Menu v-else />
            </el-icon>
          </button>
          <el-breadcrumb v-if="breadcrumbs.length > 0" class="header-breadcrumb" separator="/">
            <el-breadcrumb-item v-for="item in breadcrumbs" :key="item.label" :to="item.to">
              {{ item.label }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <h1 class="header-title">{{ pageTitle }}</h1>
        <el-link class="header-api-link" href="http://127.0.0.1:8000/docs" target="_blank" type="primary">
          API 文档 ↗
        </el-link>
      </el-header>
      <el-main :class="['main', { 'main--full-bleed': isFullBleed }]">
        <div :class="contentShellClass">
          <router-view v-slot="{ Component, route: viewRoute }">
            <transition name="route-fade" mode="out-in">
              <component :is="Component" :key="viewRoute.fullPath" />
            </transition>
          </router-view>
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}

.aside-backdrop {
  display: none;
}

.aside {
  background: var(--color-bg-surface);
  border-right: 1px solid var(--color-border);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--spacing-8);
  box-sizing: border-box;
  height: 72px;
  padding: 20px var(--spacing-16);
  color: inherit;
  text-decoration: none;
}

.brand-name {
  font-family: var(--font-sans);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--color-text-primary);
}

.tag {
  font-size: var(--text-caption-size);
  background: var(--color-primary-light);
  color: var(--color-primary);
  padding: 2px var(--spacing-8);
  border-radius: var(--radius-sm);
}

.menu {
  border-right: none;
  background: transparent;
}

.menu :deep(.el-menu-item) {
  display: flex;
  align-items: center;
  gap: var(--spacing-12);
  height: 44px;
  margin: 0;
  padding: 0 var(--spacing-16);
  border-left: 3px solid transparent;
  color: var(--color-text-primary);
  transition:
    background-color var(--transition-instant),
    color var(--transition-instant),
    border-color var(--transition-instant);
}

.menu :deep(.el-menu-item:hover) {
  background-color: var(--color-bg-page);
  color: var(--color-text-primary);
}

.menu :deep(.el-menu-item.is-active) {
  background-color: var(--color-primary-light);
  border-left-color: var(--color-primary);
  color: var(--color-primary);
}

.menu :deep(.el-menu-item.is-active .el-icon) {
  color: var(--color-primary);
}

.nav-icon {
  width: 20px;
  height: 20px;
  font-size: 20px;
  flex-shrink: 0;
}

.nav-label {
  font-size: var(--text-body-size);
  line-height: 1;
}

.header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: var(--spacing-16);
  height: 56px;
  padding: 0 var(--spacing-32);
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
}

.header-start {
  display: flex;
  align-items: center;
  gap: var(--spacing-12);
  min-width: 0;
  justify-self: start;
}

.header-menu-toggle {
  display: none;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    background-color var(--transition-instant),
    border-color var(--transition-instant),
    color var(--transition-instant);
}

.header-menu-toggle:hover {
  background: var(--color-bg-page);
  border-color: var(--color-border-strong);
}

.header-menu-toggle:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.header-menu-toggle__icon {
  width: 18px;
  height: 18px;
  font-size: 18px;
}

.header-breadcrumb {
  font-size: var(--text-caption-size);
  line-height: var(--text-caption-leading);
}

.header-title {
  margin: 0;
  justify-self: center;
  font-family: var(--font-sans);
  font-size: 16px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-text-primary);
}

.header-api-link {
  justify-self: end;
  font-size: var(--text-body-size);
}

.main-column {
  background: var(--color-bg-page);
}

.main {
  padding: var(--spacing-24) var(--spacing-32);
  background: var(--color-bg-page);
}

.main--full-bleed {
  padding: 0;
}

.shell-content--full-bleed {
  min-height: calc(100vh - 56px);
}

@media (max-width: 767px) {
  .aside-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: calc(var(--z-drawer) - 1);
    background: rgb(15 23 42 / 35%);
  }

  .aside {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: var(--z-drawer);
    transform: translateX(-100%);
    transition: transform var(--transition-slow);
  }

  .aside--open {
    transform: translateX(0);
  }

  .header-menu-toggle {
    display: inline-flex;
  }

  .header {
    padding: 0 var(--spacing-16);
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .main {
    padding: var(--spacing-16);
  }
}

@media (prefers-reduced-motion: reduce) {
  .aside {
    transition: none;
  }
}
</style>

<style>
.route-fade-enter-active,
.route-fade-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-out-product),
    transform var(--duration-normal) var(--ease-out-product);
}

.route-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.route-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (prefers-reduced-motion: reduce) {
  .route-fade-enter-active,
  .route-fade-leave-active {
    transition: none;
  }

  .route-fade-enter-from,
  .route-fade-leave-to {
    opacity: 1;
    transform: none;
  }
}
</style>
