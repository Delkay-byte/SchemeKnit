'use client'

/**
 * SchemeKnit Error Normalizer
 *
 * Maps common HTTP/network errors to friendly, teacher-facing messages.
 * Prevents raw error dumps from reaching the UI.
 */

export type ErrorCategory =
  | 'network'
  | 'maintenance'
  | 'auth'
  | 'entitlement'
  | 'validation'
  | 'rate_limit'
  | 'server'
  | 'unknown'

export interface NormalizedError {
  category: ErrorCategory
  message: string
  technical: string
  canRetry: boolean
  showBanner: boolean
}

const FRIENDLY_MESSAGES: Record<ErrorCategory, string> = {
  network: 'SchemeKnit server is currently unavailable. We\'ll reconnect automatically.',
  maintenance: 'SchemeKnit is currently undergoing maintenance. We\'ll be back shortly.',
  auth: 'Please sign in to continue.',
  entitlement: 'This feature requires an upgrade. Please check your current plan.',
  validation: 'Please check your input and try again.',
  rate_limit: 'Too many requests. Please wait a moment and try again.',
  server: 'We couldn\'t complete that request. Please try again.',
  unknown: 'Something unexpected happened. Please try again.',
}

export function normalizeError(error: unknown): NormalizedError {
  const technical = extractTechnicalMessage(error)

  // Network errors (fetch failures, DNS, CORS)
  if (isNetworkError(error)) {
    return {
      category: 'network',
      message: FRIENDLY_MESSAGES.network,
      technical,
      canRetry: true,
      showBanner: true,
    }
  }

  // HTTP status-based classification
  const status = extractHttpStatus(error)

  if (status === 503) {
    // Could be maintenance or server overload
    const body = extractResponseBody(error)
    if (body?.status === 'maintenance' || body?.maintenance?.active) {
      return {
        category: 'maintenance',
        message: body?.maintenance?.message || FRIENDLY_MESSAGES.maintenance,
        technical,
        canRetry: true,
        showBanner: true,
      }
    }
    return {
      category: 'server',
      message: 'SchemeKnit server is temporarily unavailable. Please try again in a moment.',
      technical,
      canRetry: true,
      showBanner: true,
    }
  }

  if (status === 401 || status === 403) {
    return {
      category: 'auth',
      message: FRIENDLY_MESSAGES.auth,
      technical,
      canRetry: false,
      showBanner: false,
    }
  }

  if (status === 403) {
    // Check if it's an entitlement issue
    const body = extractResponseBody(error)
    if (body?.detail?.includes('generation limit') || body?.detail?.includes('entitlement')) {
      return {
        category: 'entitlement',
        message: body.detail,
        technical,
        canRetry: false,
        showBanner: false,
      }
    }
    return {
      category: 'auth',
      message: 'You don\'t have permission for this action.',
      technical,
      canRetry: false,
      showBanner: false,
    }
  }

  if (status === 422) {
    return {
      category: 'validation',
      message: FRIENDLY_MESSAGES.validation,
      technical,
      canRetry: false,
      showBanner: false,
    }
  }

  if (status === 429) {
    return {
      category: 'rate_limit',
      message: FRIENDLY_MESSAGES.rate_limit,
      technical,
      canRetry: true,
      showBanner: false,
    }
  }

  if (status >= 500) {
    return {
      category: 'server',
      message: FRIENDLY_MESSAGES.server,
      technical,
      canRetry: true,
      showBanner: false,
    }
  }

  return {
    category: 'unknown',
    message: FRIENDLY_MESSAGES.unknown,
    technical,
    canRetry: true,
    showBanner: false,
  }
}

function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError) {
    return error.message.includes('fetch') ||
           error.message.includes('network') ||
           error.message.includes('Failed to fetch') ||
           error.message.includes('NetworkError')
  }
  if (error instanceof DOMException) {
    return error.name === 'AbortError' || error.name === 'NetworkError'
  }
  return false
}

function extractHttpStatus(error: unknown): number {
  if (error instanceof Response) return error.status
  if (error instanceof Error) {
    const match = error.message.match(/status[:\s]*(\d{3})/i)
    if (match) return parseInt(match[1], 10)
  }
  // Check for common error patterns
  const msg = String(error).toLowerCase()
  if (msg.includes('401')) return 401
  if (msg.includes('403')) return 403
  if (msg.includes('404')) return 404
  if (msg.includes('422')) return 422
  if (msg.includes('429')) return 429
  if (msg.includes('500')) return 500
  if (msg.includes('502')) return 502
  if (msg.includes('503')) return 503
  return 0
}

function extractTechnicalMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return String(error)
}

function extractResponseBody(error: unknown): any {
  try {
    if (error instanceof Response) {
      // Can't read body synchronously, but we might have it cached
      return null
    }
    if (error instanceof Error) {
      const match = error.message.match(/\{.*\}/)
      if (match) return JSON.parse(match[0])
    }
  } catch {}
  return null
}

/**
 * Show a toast notification for an error.
 * Uses the existing toast system but with normalized messages.
 */
export function showErrorToast(error: unknown, toast: (opts: any) => void) {
  const normalized = normalizeError(error)

  // Don't show toast for network errors (banner handles it)
  if (normalized.category === 'network' || normalized.category === 'maintenance') {
    return
  }

  toast({
    title: normalized.category === 'auth' ? 'Authentication Required' :
           normalized.category === 'entitlement' ? 'Plan Upgrade Required' :
           normalized.category === 'validation' ? 'Validation Error' :
           'Error',
    description: normalized.message,
    variant: normalized.category === 'server' ? 'destructive' : 'default',
  })
}
