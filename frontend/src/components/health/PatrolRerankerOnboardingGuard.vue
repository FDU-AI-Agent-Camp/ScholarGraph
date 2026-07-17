<!--
Copyright 2026 FDU-AI-Agent-Camp
SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { HEALTH_BASELINE_COPY } from '@/constants/healthCopy'
import { useHealthStore } from '@/stores/health'

const route = useRoute()
const healthStore = useHealthStore()

const showBanner = computed(() => healthStore.shouldWarnOnRoute(route.path))

const showModal = computed({
  get: () => healthStore.showPatrolOnboardingModal,
  set: (value: boolean) => {
    if (!value) {
      healthStore.dismissPatrolOnboarding()
    }
  },
})

function onConfirmModal(): void {
  healthStore.dismissPatrolOnboarding()
}
</script>

<template>
  <div v-if="showBanner" class="patrol-health-guard">
    <el-alert
      class="patrol-health-guard__banner"
      type="warning"
      :title="HEALTH_BASELINE_COPY.rerankerBannerTitle"
      :description="HEALTH_BASELINE_COPY.rerankerBannerDescription"
      show-icon
      :closable="false"
    />
  </div>

  <el-dialog
    v-model="showModal"
    class="patrol-health-guard__dialog"
    :title="HEALTH_BASELINE_COPY.rerankerModalTitle"
    width="520px"
    :close-on-click-modal="false"
    append-to-body
  >
    <p class="text-body patrol-health-guard__dialog-body">
      {{ HEALTH_BASELINE_COPY.rerankerBannerDescription }}
    </p>
    <template #footer>
      <el-button type="primary" @click="onConfirmModal">
        {{ HEALTH_BASELINE_COPY.rerankerModalConfirm }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.patrol-health-guard__banner {
  margin-bottom: var(--spacing-16);
}

.patrol-health-guard__dialog-body {
  margin: 0;
  color: var(--color-text-secondary);
}
</style>
