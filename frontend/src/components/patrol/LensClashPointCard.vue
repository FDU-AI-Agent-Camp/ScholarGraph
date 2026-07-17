<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import type { components } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

type LensClashPoint = components['schemas']['LensClashPoint']

defineProps<{
  point: LensClashPoint
}>()
</script>

<template>
  <article class="patrol-point-card patrol-point-card--lens_clash">
    <dl class="patrol-point-card__fields">
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldLensA }}</dt>
        <dd>{{ point.lens_a }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldLensB }}</dt>
        <dd>{{ point.lens_b }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldAspect }}</dt>
        <dd>{{ point.clash_aspect }}</dd>
      </div>
    </dl>
  </article>
</template>

<style src="./patrolPointCard.css"></style>
