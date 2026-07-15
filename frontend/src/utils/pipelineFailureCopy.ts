/** Map failed pipeline error_code → short Chinese alert titles. */

export const PROCESS_ORPHANED_CODE = 'PROCESS_ORPHANED' as const
export const PROCESS_TIMEOUT_CODE = 'PROCESS_TIMEOUT' as const

export const PROCESS_ORPHANED_TITLE = '解析中断' as const
export const PROCESS_TIMEOUT_TITLE = '解析超时' as const

const PIPELINE_FAILURE_TITLES: Readonly<Record<string, string>> = {
  [PROCESS_ORPHANED_CODE]: PROCESS_ORPHANED_TITLE,
  [PROCESS_TIMEOUT_CODE]: PROCESS_TIMEOUT_TITLE,
}

/**
 * Resolve the failed-status alert title.
 * Known orphan/timeout codes use Chinese titles; unknown codes keep the machine code.
 */
export function resolvePipelineFailureTitle(errorCode: string | null | undefined): string {
  if (!errorCode?.trim()) {
    return 'PIPELINE_FAILED'
  }
  return PIPELINE_FAILURE_TITLES[errorCode] ?? errorCode
}
