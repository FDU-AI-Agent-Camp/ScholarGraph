<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const active = computed(() => route.path)
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
        <span>学术论文逻辑解构 · 开发骨架</span>
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
  background: #fff;
  border-right: 1px solid #e5e7eb;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 16px 8px;
  color: inherit;
}
.tag {
  font-size: 12px;
  background: #e8eefc;
  color: #1a56db;
  padding: 2px 6px;
  border-radius: 4px;
}
.menu {
  border-right: none;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.main {
  padding: 20px 24px;
}
</style>
