/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { defineStore } from 'pinia'
import { ref, type Ref } from 'vue'

export interface AppStoreState {
  sidebarCollapsed: Ref<boolean>
  toggleSidebar: () => void
}

export const useAppStore = defineStore('app', (): AppStoreState => {
  const sidebarCollapsed = ref(false)

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { sidebarCollapsed, toggleSidebar }
})
