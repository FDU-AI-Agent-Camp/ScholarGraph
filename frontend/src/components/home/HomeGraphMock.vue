<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
interface MockNode {
  id: string
  x: number
  y: number
  label: string
}

interface MockEdge {
  from: string
  to: string
}

interface MockInsight {
  title: string
  summary: string
}

const mockNodes: MockNode[] = [
  { id: 'n1', x: 72, y: 48, label: '核心论点' },
  { id: 'n2', x: 220, y: 40, label: '理论框架' },
  { id: 'n3', x: 360, y: 56, label: '方法设计' },
  { id: 'n4', x: 120, y: 140, label: '分析视角' },
  { id: 'n5', x: 280, y: 128, label: '实验流程' },
  { id: 'n6', x: 400, y: 156, label: '结论' },
  { id: 'n7', x: 56, y: 228, label: '引用链' },
]

const mockEdges: MockEdge[] = [
  { from: 'n1', to: 'n2' },
  { from: 'n2', to: 'n3' },
  { from: 'n1', to: 'n4' },
  { from: 'n4', to: 'n5' },
  { from: 'n5', to: 'n6' },
  { from: 'n4', to: 'n7' },
  { from: 'n3', to: 'n6' },
]

const mockInsights: MockInsight[] = [
  { title: 'Lens Clash', summary: '消费社会 vs public sphere' },
  { title: '视角差异', summary: '理论框架与实证路径不一致' },
]

const nodeMap = Object.fromEntries(mockNodes.map((node) => [node.id, node])) as Record<string, MockNode>

function edgePath(edge: MockEdge): string {
  const from = nodeMap[edge.from]
  const to = nodeMap[edge.to]
  if (!from || !to) {
    return ''
  }
  return `M ${from.x + 44} ${from.y + 18} L ${to.x + 4} ${to.y + 18}`
}
</script>

<template>
  <div class="home-graph-mock">
    <div class="home-graph-mock__graph-area">
      <svg class="home-graph-mock__canvas" viewBox="0 0 520 300" aria-hidden="true">
        <defs>
          <marker id="home-graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" fill="var(--color-text-muted)" />
          </marker>
        </defs>
        <g class="home-graph-mock__edges">
          <path
            v-for="(edge, index) in mockEdges"
            :key="`${edge.from}-${edge.to}-${index}`"
            :d="edgePath(edge)"
            class="home-graph-mock__edge"
            marker-end="url(#home-graph-arrow)"
          />
        </g>
        <g class="home-graph-mock__nodes">
          <g v-for="node in mockNodes" :key="node.id" :transform="`translate(${node.x} ${node.y})`">
            <rect class="home-graph-mock__node" width="88" height="36" rx="8" ry="8" />
            <text class="home-graph-mock__node-label" x="44" y="23" text-anchor="middle">{{ node.label }}</text>
          </g>
        </g>
      </svg>
    </div>
    <div class="home-graph-mock__insights" aria-hidden="true">
      <article v-for="item in mockInsights" :key="item.title" class="home-graph-mock__insight">
        <h3 class="home-graph-mock__insight-title">{{ item.title }}</h3>
        <p class="home-graph-mock__insight-summary">{{ item.summary }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.home-graph-mock {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 520px;
  min-height: 420px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-2xl);
  background: var(--color-bg-canvas);
  overflow: hidden;
}

.home-graph-mock__graph-area {
  flex: 0 0 auto;
  height: 300px;
  border-bottom: 1px solid var(--color-border);
}

.home-graph-mock__canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.home-graph-mock__edge {
  fill: none;
  stroke: var(--color-border-strong);
  stroke-width: 1.5;
}

.home-graph-mock__node {
  fill: var(--color-bg-surface);
  stroke: var(--color-primary-hover);
  stroke-width: 1.5;
}

.home-graph-mock__node-label {
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  fill: var(--color-text-primary);
}

.home-graph-mock__insights {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-12);
  padding: var(--spacing-16);
  background: var(--color-bg-surface);
}

.home-graph-mock__insight {
  padding: var(--spacing-12) var(--spacing-16);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-md);
}

.home-graph-mock__insight-title {
  margin: 0;
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  font-weight: 600;
  line-height: var(--text-caption-leading);
  color: var(--color-text-primary);
}

.home-graph-mock__insight-summary {
  margin: var(--spacing-4) 0 0;
  font-family: var(--font-sans);
  font-size: var(--text-caption-size);
  line-height: var(--text-caption-leading);
  color: var(--color-text-secondary);
}
</style>
