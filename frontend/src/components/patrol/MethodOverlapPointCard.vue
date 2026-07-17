<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { components } from '@/api/types'
import { PATROL_BASELINE_COPY } from '@/constants/patrolCopy'
import { isUsablePatrolNodeRef, patrolGraphLinkForNodeRef, patrolNodeRefKey } from '@/utils/patrolViewHelpers'

type MethodOverlapPoint = components['schemas']['MethodOverlapPoint']

const props = defineProps<{
  point: MethodOverlapPoint
}>()

const usableNodeRefs = computed(() => (props.point.node_refs ?? []).filter(isUsablePatrolNodeRef))
</script>

<template>
  <article class="patrol-point-card patrol-point-card--method_overlap">
    <header class="patrol-point-card__header">
      <span class="patrol-point-card__label">{{ point.overlap_label }}</span>
      <span class="text-caption patrol-point-card__type">{{ point.overlap_type }}</span>
    </header>
    <dl class="patrol-point-card__fields">
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldPaperA }}</dt>
        <dd>{{ point.paper_a_usage }}</dd>
      </div>
      <div class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldPaperB }}</dt>
        <dd>{{ point.paper_b_usage }}</dd>
      </div>
      <div v-if="point.dataset_a || point.dataset_b" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldDataset }}</dt>
        <dd>{{ [point.dataset_a, point.dataset_b].filter(Boolean).join(' · ') }}</dd>
      </div>
      <div v-if="point.overlap_score != null" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldScore }}</dt>
        <dd class="text-mono">{{ point.overlap_score }}</dd>
      </div>
      <div v-if="point.match_type" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldMatch }}</dt>
        <dd>{{ point.match_type }}</dd>
      </div>
      <div v-if="point.evidence_summary" class="patrol-point-card__row">
        <dt>{{ PATROL_BASELINE_COPY.pointFieldEvidence }}</dt>
        <dd>{{ point.evidence_summary }}</dd>
      </div>
    </dl>
    <div v-if="usableNodeRefs.length" class="patrol-point-card__node-refs">
      <RouterLink
        v-for="nodeRef in usableNodeRefs"
        :key="patrolNodeRefKey(nodeRef)"
        :to="patrolGraphLinkForNodeRef(nodeRef)"
        class="patrol-point-node-ref text-body"
        data-testid="patrol-point-node-ref"
      >
        <span class="patrol-point-node-ref__label">{{ nodeRef.label || nodeRef.node_id }}</span>
        <span class="text-mono patrol-point-node-ref__meta"> ({{ nodeRef.paper_id }} · {{ nodeRef.node_id }}) </span>
        <span class="patrol-point-node-ref__action">{{ PATROL_BASELINE_COPY.nodeRefGraphLink }}</span>
      </RouterLink>
    </div>
  </article>
</template>

<style src="./patrolPointCard.css"></style>
