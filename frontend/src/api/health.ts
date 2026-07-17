/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import { getData, type ScholarGraphAxiosRequestConfig } from './client'
import type { DataResponse, HealthData } from './types'

export async function fetchHealth(): Promise<DataResponse<HealthData>> {
  const config: ScholarGraphAxiosRequestConfig = { suppressErrorToast: true }
  return getData<HealthData>('/health', config)
}
