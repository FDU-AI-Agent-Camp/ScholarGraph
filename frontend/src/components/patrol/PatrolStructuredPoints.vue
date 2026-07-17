<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import type { PatrolPoint } from '@/api/types'

import ClaimEvolutionPointCard from '@/components/patrol/ClaimEvolutionPointCard.vue'
import ContradictionPointCard from '@/components/patrol/ContradictionPointCard.vue'
import LensClashPointCard from '@/components/patrol/LensClashPointCard.vue'
import MethodOverlapPointCard from '@/components/patrol/MethodOverlapPointCard.vue'

defineProps<{
  points: PatrolPoint[]
}>()

function pointKey(point: PatrolPoint, index: number): string {
  return `${point.mode}:${index}`
}
</script>

<template>
  <div v-if="points.length" class="patrol-structured-points" data-testid="patrol-structured-points">
    <template v-for="(point, index) in points" :key="pointKey(point, index)">
      <MethodOverlapPointCard v-if="point.mode === 'method_overlap'" :point="point" />
      <ClaimEvolutionPointCard v-else-if="point.mode === 'claim_evolution'" :point="point" />
      <LensClashPointCard v-else-if="point.mode === 'lens_clash'" :point="point" />
      <ContradictionPointCard v-else-if="point.mode === 'contradiction'" :point="point" />
      <!-- Unknown discriminators are skipped (boundary: no throw, no leak). -->
    </template>
  </div>
</template>

<style scoped>
.patrol-structured-points {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-12);
  margin-top: var(--spacing-16);
}
</style>
