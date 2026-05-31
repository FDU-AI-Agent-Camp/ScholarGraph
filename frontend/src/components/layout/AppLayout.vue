<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const active = computed(() => route.path)
const pageTitle = computed(() => route.meta.title ?? 'ScholarGraph')
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <router-link class="brand" to="/">
        <strong>ScholarGraph</strong>
        <span class="tag">V1</span>
      </router-link>
      <el-menu :default-active="active" router class="menu">
        <el-menu-item index="/">工作台</el-menu-item>
        <el-menu-item index="/papers">文献库</el-menu-item>
        <el-menu-item index="/patrol">共同体巡检</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>{{ pageTitle }} · 学术论文逻辑解构</span>
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
  padding: 20px var(--spacing-16) var(--spacing-8);
  color: inherit;
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
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
}
.main {
  padding: var(--spacing-24) var(--spacing-32);
  background: var(--color-bg-page);
}
</style>
