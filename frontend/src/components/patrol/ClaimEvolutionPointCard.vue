<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import type { components } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'

type ClaimEvolutionPoint = components['schemas']['ClaimEvolutionPoint']

defineProps<{
  point: ClaimEvolutionPoint
}>()
</script>

<template>
  <article class="patrol-point-card patrol-point-card--claim_evolution">
    <header class="patrol-point-card__header">
      <span class="patrol-point-card__label">{{ point.research_question }}</span>
      <span v-if="point.evolution_type" class="text-caption patrol-point-card__type">
        {{ point.evolution_type }}
      </span>
    </header>
    <dl class="patrol-point-card__fields">
      <div v-if="point.paper_a_claim" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldPaperA }}</dt>
        <dd>{{ point.paper_a_claim }}</dd>
      </div>
      <div v-if="point.paper_b_claim" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldPaperB }}</dt>
        <dd>{{ point.paper_b_claim }}</dd>
      </div>
      <div v-if="point.problem_fit_score != null" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldFit }}</dt>
        <dd class="text-mono">{{ point.problem_fit_score }}</dd>
      </div>
      <div v-if="point.evidence_summary" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldEvidence }}</dt>
        <dd>{{ point.evidence_summary }}</dd>
      </div>
    </dl>
  </article>
</template>

<style src="./patrolPointCard.css"></style>
