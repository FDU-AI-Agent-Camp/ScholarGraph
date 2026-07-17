/**
 * Copyright 2026 FDU-AI-Agent-Camp
 * SPDX-License-Identifier: Apache-2.0
 */

import type { UploadRequestOptions } from 'element-plus'
import { vi } from 'vitest'

export function triggerPdfUpload(httpRequest: (options: UploadRequestOptions) => void): void {
  const file = new File(['%PDF'], 'sample.pdf', { type: 'application/pdf' })
  void httpRequest({
    file,
    onSuccess: vi.fn(),
    onError: vi.fn(),
  } as unknown as UploadRequestOptions)
}

export function triggerNonPdfUpload(httpRequest: (options: UploadRequestOptions) => void): void {
  const file = new File(['text'], 'notes.txt', { type: 'text/plain' })
  void httpRequest({
    file,
    onSuccess: vi.fn(),
    onError: vi.fn(),
  } as unknown as UploadRequestOptions)
}
