<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div>
    <h1>ScholarGraph 工作台</h1>
    <p>前后端通用骨架已就绪，各角色在约定目录内扩展功能即可。</p>
    <el-space wrap>
      <el-button type="primary">
        <RouterLink to="/papers">进入文献库</RouterLink>
      </el-button>
      <el-button>
        <RouterLink to="/patrol">共同体巡检</RouterLink>
      </el-button>
    </el-space>
    <el-divider />
    <el-descriptions title="本地联调" :column="1" border>
      <el-descriptions-item label="前端">npm run dev → http://localhost:5173</el-descriptions-item>
      <el-descriptions-item label="后端">uv run uvicorn backend.main:app --reload</el-descriptions-item>
      <el-descriptions-item label="契约">docs/api/openapi.yaml、docs/v1/api-contract.md</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<style scoped>
h1 {
  margin-top: 0;
}
a {
  color: inherit;
}
</style>
