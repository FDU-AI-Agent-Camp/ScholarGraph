<script setup lang="ts">
import { Document, HomeFilled, Search } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

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

function handleNavSelect(index: string): void {
  void router.push(index)
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="240px" class="aside">
      <router-link class="brand" to="/">
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
        <span class="header-title">{{ pageTitle }} · 学术论文逻辑解构</span>
        <el-link href="http://127.0.0.1:8000/docs" target="_blank" type="primary">API 文档</el-link>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--spacing-32);
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
}

.header-title {
  font-size: 16px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-text-primary);
}

.main-column {
  background: var(--color-bg-page);
}

.main {
  padding: var(--spacing-24) var(--spacing-32);
  background: var(--color-bg-page);
}
</style>
