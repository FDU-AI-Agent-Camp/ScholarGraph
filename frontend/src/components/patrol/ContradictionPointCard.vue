<script setup lang="ts">
import type { components } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

type ContradictionPoint = components['schemas']['ContradictionPoint']

defineProps<{
  point: ContradictionPoint
}>()
</script>

<template>
  <article class="patrol-point-card patrol-point-card--contradiction">
    <dl class="patrol-point-card__fields">
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldPointA }}</dt>
        <dd>{{ point.point_a }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldPointB }}</dt>
        <dd>{{ point.point_b }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldConflict }}</dt>
        <dd>{{ point.conflict_type }}</dd>
      </div>
    </dl>
  </article>
</template>

<style src="./patrolPointCard.css"></style>
