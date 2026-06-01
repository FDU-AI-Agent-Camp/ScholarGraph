<script setup lang="ts">
import { ChatDotRound, Connection, Upload } from '@element-plus/icons-vue'
import type { Component } from 'vue'
import { RouterLink } from 'vue-router'

import HomeGraphMock from '@/components/home/HomeGraphMock.vue'
import BadgeParadigm from '@/components/ui/BadgeParadigm.vue'

interface HomeStep {
  label: string
  icon: Component
}

const HOME_EYEBROW = 'AI AGENT · GRAPH RAG'
const HOME_TITLE_LINES = ['解构论文逻辑，', '发现学术共同体'] as const
const HOME_SUBTITLE = '面向 HSS 与 STEM 双范式分流：上传 PDF 后自动建图，在同一工作台完成多尺度问答与共同体巡检。'
const HOME_PARADIGM_CAPTION = 'HSS 侧重理论视角与文本论证；STEM 侧重方法、实验与可复现流程。'

const homeSteps: HomeStep[] = [
  { label: '上传 PDF', icon: Upload },
  { label: '自动建图', icon: Connection },
  { label: '问答·巡检', icon: ChatDotRound },
]
</script>

<template>
  <div class="home page-content">
    <div class="home-hero">
      <section class="home-copy">
        <p class="home-eyebrow">{{ HOME_EYEBROW }}</p>
        <h1 class="text-display home-title">
          <span v-for="line in HOME_TITLE_LINES" :key="line" class="home-title-line">{{ line }}</span>
        </h1>
        <p class="text-body-lg home-subtitle">{{ HOME_SUBTITLE }}</p>
        <div class="home-ctas">
          <RouterLink v-slot="{ navigate }" to="/papers" custom>
            <el-button type="primary" @click="navigate">上传论文</el-button>
          </RouterLink>
          <RouterLink v-slot="{ navigate }" to="/papers" custom>
            <el-button plain @click="navigate">浏览文献库</el-button>
          </RouterLink>
        </div>
        <ol class="home-steps" aria-label="使用流程">
          <li v-for="step in homeSteps" :key="step.label" class="home-step">
            <span class="home-step-icon" aria-hidden="true">
              <el-icon><component :is="step.icon" /></el-icon>
            </span>
            <span class="home-step-label">{{ step.label }}</span>
          </li>
        </ol>
        <div class="home-paradigms">
          <div class="home-paradigms-badges">
            <BadgeParadigm paradigm="HSS" />
            <BadgeParadigm paradigm="STEM" />
          </div>
          <p class="home-paradigms-caption">{{ HOME_PARADIGM_CAPTION }}</p>
        </div>
      </section>
      <aside class="home-visual" aria-label="逻辑图谱装饰预览">
        <HomeGraphMock />
      </aside>
    </div>

    <section class="home-quick-links" aria-label="快速入口">
      <article class="home-quick-card">
        <h2 class="text-h2 home-quick-card__title">Lens Clash 巡检</h2>
        <p class="text-body home-quick-card__body">跨两篇 ready 论文探测分析视角冲突，快速定位可深挖的 node_ref。</p>
        <RouterLink v-slot="{ navigate }" to="/patrol" custom>
          <el-button link type="primary" @click="navigate">查看巡检演示</el-button>
        </RouterLink>
      </article>
      <article class="home-quick-card">
        <h2 class="text-h2 home-quick-card__title">多尺度问答</h2>
        <p class="text-body home-quick-card__body">在详情页用 SSE 流式问答，Citation Tag 与图谱节点 150ms 联动高亮。</p>
        <RouterLink v-slot="{ navigate }" to="/papers/hss-001" custom>
          <el-button link type="primary" @click="navigate">打开示例论文</el-button>
        </RouterLink>
      </article>
    </section>
  </div>
</template>

<style scoped>
.home {
  padding-top: var(--spacing-48);
}

.home-hero {
  display: grid;
  grid-template-columns: 58fr 42fr;
  gap: var(--spacing-32);
  align-items: start;
}

.home-copy {
  min-width: 0;
}

.home-eyebrow {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  font-weight: var(--text-caption-weight);
  line-height: var(--text-caption-leading);
  letter-spacing: 0.08em;
  color: var(--color-primary);
}

.home-title {
  margin: var(--spacing-16) 0 0;
  color: var(--color-text-primary);
}

.home-title-line {
  display: block;
}

.home-subtitle {
  max-width: 480px;
  margin: var(--spacing-16) 0 0;
  color: var(--color-text-secondary);
}

.home-ctas {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-12);
  margin-top: var(--spacing-24);
}

.home-steps {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-32);
  margin: var(--spacing-48) 0 0;
  padding: 0;
  list-style: none;
}

.home-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-12);
  min-width: 72px;
  text-align: center;
}

.home-step-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: var(--text-h2-size);
}

.home-step-label {
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  line-height: var(--text-body-leading);
  color: var(--color-text-primary);
}

.home-paradigms {
  margin-top: var(--spacing-32);
}

.home-paradigms-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-8);
}

.home-paradigms-caption {
  margin: var(--spacing-12) 0 0;
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  line-height: var(--text-caption-leading);
  color: var(--color-text-secondary);
}

.home-visual {
  display: flex;
  justify-content: flex-end;
  min-width: 0;
}

.home-quick-links {
  display: grid;
  grid-template-columns: 60fr 40fr;
  gap: var(--spacing-24);
  margin-top: var(--spacing-64);
}

.home-quick-card {
  box-sizing: border-box;
  padding: var(--spacing-24);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
  transition:
    box-shadow var(--transition-instant),
    border-color var(--transition-instant);
}

.home-quick-card:hover {
  border-color: var(--color-primary-muted);
  box-shadow: var(--shadow-md);
}

.home-quick-card__title {
  margin: 0;
  color: var(--color-text-primary);
}

.home-quick-card__body {
  margin: var(--spacing-12) 0 var(--spacing-16);
  color: var(--color-text-secondary);
}
</style>
