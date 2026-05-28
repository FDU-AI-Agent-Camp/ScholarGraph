import { isApiClientError } from '@/api/client'

/** User-facing message from an unknown thrown value. */
export function getUnknownErrorMessage(error: unknown): string {
  if (isApiClientError(error)) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return '未知错误'
}

/** Log API/store failures without assuming Error shape. */
export function logUnknownError(context: string, error: unknown): void {
  if (isApiClientError(error)) {
    console.error(`[${context}]`, error.code, error.message)
    return
  }
  if (error instanceof Error) {
    console.error(`[${context}]`, error.message)
    return
  }
  console.error(`[${context}]`, error)
}
