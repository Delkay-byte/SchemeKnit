'use client'

/**
 * SchemeKnit Error Normalizer
 *
 * Maps HTTP, API and network failures to friendly, teacher-facing messages.
 * Raw server diagnostics stay in `technical` for internal logging only and are
 * never rendered.
 */

import type { ApiError } from './api'

export type ErrorCategory =
  | 'network'
  | 'timeout'
  | 'maintenance'
  | 'auth'
  | 'permission'
  | 'entitlement'
  | 'validation'
  | 'not_found'
  | 'conflict'
  | 'too_large'
  | 'unsupported'
  | 'rate_limit'
  | 'server'
  | 'unknown'

export interface NormalizedError {
  category: ErrorCategory
  message: string
  technical: string
  canRetry: boolean
  showBanner: boolean
  status: number
  code?: string
  requestId?: string
  retryAfterSeconds?: number
}

const FRIENDLY_MESSAGES: Record<ErrorCategory, string> = {
  network: "We couldn't connect to SchemeKnit. Check your internet connection and try again.",
  timeout: 'SchemeKnit took too long to respond. Check your connection and try again.',
  maintenance: "SchemeKnit is undergoing maintenance. We'll be back shortly.",
  auth: 'Your session has expired. Please sign in again.',
  permission: "You don't have permission to perform this action.",
  entitlement: 'This feature is not included in your current plan.',
  validation: 'Some details are missing or incorrect. Please review the highlighted fields.',
  not_found: "We couldn't find this item. It may have been removed.",
  conflict: 'This item has changed since you opened it. Refresh the latest version before saving.',
  too_large: 'This file is too large. Choose a smaller file and try again.',
  unsupported: 'This file format is not supported. Please choose a supported document.',
  rate_limit: 'Too many requests. Please wait a moment before trying again.',
  server: 'SchemeKnit is temporarily unavailable. Please try again.',
  unknown: "Something went wrong. Your unsaved work has been kept where possible.",
}

const INTERNAL_MARKERS =
  /(traceback|psycopg|sqlalchemy|stack trace|exception at|internal server|sqlstate|select .* from|insert into)/i

function safeDetail(error: unknown): string | null {
  const candidate =
    typeof error === 'string'
      ? error
      : error && typeof error === 'object' && typeof (error as { message?: unknown }).message === 'string'
        ? (error as { message: string }).message
        : null
  if (!candidate) return null
  const text = candidate.trim()
  if (!text || text.length > 300 || text.includes('\n')) return null
  if (INTERNAL_MARKERS.test(text)) return null
  return text
}

function apiError(error: unknown): ApiError | null {
  if (error && typeof error === 'object' && 'message' in error) {
    const candidate = error as ApiError
    if (typeof candidate.status === 'number') return candidate
  }
  return null
}

function errorBody(error: unknown): Record<string, unknown> | null {
  const direct = apiError(error)
  if (direct?.details && typeof direct.details === 'object') {
    return direct.details as Record<string, unknown>
  }
  if (error instanceof Response) return null
  if (error instanceof Error) {
    const match = error.message.match(/\{[\s\S]*\}/)
    if (match) {
      try {
        const parsed = JSON.parse(match[0])
        return parsed && typeof parsed === 'object' ? parsed : null
      } catch {
        return null
      }
    }
  }
  return null
}

function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError) {
    const text = error.message.toLowerCase()
    return text.includes('fetch') || text.includes('network') || text.includes('load failed')
  }
  if (error instanceof DOMException) {
    return error.name === 'NetworkError'
  }
  return false
}

function isTimeoutError(error: unknown): boolean {
  if (error instanceof DOMException) return error.name === 'AbortError'
  if (error instanceof Error) {
    return error.name === 'TimeoutError' || /timed?\s*out|timeout/i.test(error.message)
  }
  return false
}

function extractHttpStatus(error: unknown): number {
  const direct = apiError(error)
  if (direct && typeof direct.status === 'number') return direct.status
  if (error instanceof Response) return error.status
  if (error instanceof Error) {
    const match = error.message.match(/status[:\s]*(\d{3})/i)
    if (match) return parseInt(match[1], 10)
  }
  const message = String(error)
  const known = message.match(/\b(401|403|404|409|413|415|422|429|500|502|503|504)\b/)
  return known ? parseInt(known[1], 10) : 0
}

function extractTechnicalMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return String(error)
}

export function normalizeError(error: unknown): NormalizedError {
  const technical = extractTechnicalMessage(error)
  const status = extractHttpStatus(error)
  const api = apiError(error)
  const body = errorBody(error)
  const code = typeof api?.code === 'string' ? api.code : undefined
  const requestId = api?.requestId
  const retryAfterSeconds = api?.retryAfter

  const base = {
    technical,
    status,
    code,
    requestId,
    retryAfterSeconds,
    showBanner: false,
  }

  if (isTimeoutError(error)) {
    return { ...base, category: 'timeout', message: FRIENDLY_MESSAGES.timeout, canRetry: true, showBanner: true }
  }

  if (isNetworkError(error)) {
    return { ...base, category: 'network', message: FRIENDLY_MESSAGES.network, canRetry: true, showBanner: true }
  }

  if (status === 0) {
    const detail = safeDetail(error)
    return {
      ...base,
      category: 'unknown',
      message: detail || FRIENDLY_MESSAGES.unknown,
      canRetry: true,
      showBanner: false,
    }
  }

  if (status === 401) {
    return { ...base, category: 'auth', message: FRIENDLY_MESSAGES.auth, canRetry: false, showBanner: false }
  }

  if (status === 403) {
    // Entitlement checks must run BEFORE the generic permission branch, or the
    // plan-specific guidance can never be reached.
    const detail = safeDetail(api) || safeDetail(body?.detail)
    const entitlement =
      code?.startsWith('entitlement') ||
      code?.startsWith('plan_') ||
      code === 'generation_limit' ||
      /(generation limit|entitlement|current plan|upgrade)/i.test(`${code || ''} ${detail || ''}`)
    if (entitlement) {
      return {
        ...base,
        category: 'entitlement',
        message: detail && !INTERNAL_MARKERS.test(detail)
          ? detail
          : FRIENDLY_MESSAGES.entitlement,
        canRetry: false,
        showBanner: false,
      }
    }
    return { ...base, category: 'permission', message: FRIENDLY_MESSAGES.permission, canRetry: false, showBanner: false }
  }

  if (status === 404) {
    const detail = safeDetail(api) || safeDetail(body?.detail)
    return {
      ...base,
      category: 'not_found',
      message: detail && /not found|missing|removed/i.test(detail) ? detail : FRIENDLY_MESSAGES.not_found,
      canRetry: false,
      showBanner: false,
    }
  }

  if (status === 409) {
    return { ...base, category: 'conflict', message: FRIENDLY_MESSAGES.conflict, canRetry: false, showBanner: false }
  }

  if (status === 413) {
    return { ...base, category: 'too_large', message: FRIENDLY_MESSAGES.too_large, canRetry: false, showBanner: false }
  }

  if (status === 415) {
    return { ...base, category: 'unsupported', message: FRIENDLY_MESSAGES.unsupported, canRetry: false, showBanner: false }
  }

  if (status === 422 || status === 400) {
    const detail = safeDetail(api)
    if (code?.startsWith('turnstile_')) {
      return {
        ...base,
        category: 'validation',
        message: detail || 'Bot verification failed. Please complete the challenge again.',
        canRetry: false,
        showBanner: false,
      }
    }
    const fields: string[] = Array.isArray(body?.errors)
      ? body.errors
          .map((entry) => {
            if (!entry || typeof entry !== 'object') return ''
            const field = (entry as { field?: unknown }).field
            return typeof field === 'string' ? field : ''
          })
          .filter(Boolean)
      : []
    let message = FRIENDLY_MESSAGES.validation
    if (fields.some((field) => field.includes('term_start_date') || field.includes('term_end_date'))) {
      message = 'The term dates are incomplete. Set the Term Start and Term End dates, then try again.'
    } else if (fields.some((field) => field.includes('class_level') || field.includes('subject'))) {
      message = 'The subject or class for this scheme is not set. Confirm the scheme details, then try again.'
    } else if (detail && !INTERNAL_MARKERS.test(detail)) {
      message = detail
    }
    return { ...base, category: 'validation', message, canRetry: false, showBanner: false }
  }

  if (status === 408 || status === 425) {
    return { ...base, category: 'timeout', message: FRIENDLY_MESSAGES.timeout, canRetry: true, showBanner: false }
  }

  if (status === 429) {
    return {
      ...base,
      category: 'rate_limit',
      message: retryAfterSeconds && retryAfterSeconds > 0
        ? `Too many requests. Please wait ${retryAfterSeconds} second${retryAfterSeconds === 1 ? '' : 's'} and try again.`
        : FRIENDLY_MESSAGES.rate_limit,
      canRetry: true,
      showBanner: false,
    }
  }

  if (status === 503) {
    if (body?.status === 'maintenance' || (body?.maintenance as { active?: boolean } | undefined)?.active) {
      const maintenance = body?.maintenance as { message?: unknown } | undefined
      return {
        ...base,
        category: 'maintenance',
        message: typeof maintenance?.message === 'string' && maintenance.message
          ? maintenance.message
          : FRIENDLY_MESSAGES.maintenance,
        canRetry: true,
        showBanner: true,
      }
    }
  }

  if (status >= 500) {
    // Two distinct cases (the ux-reliability E2E pins both):
    //   * 503 — a CONTROLLED refusal the teacher can act on (quality gate
    //     refused the batch, PDF converter missing, licence problem). Its
    //     detail is safe and actionable, so surface it unless it looks like an
    //     internal stack trace.
    //   * anything else (500, 502, 504) — an uncontrolled server fault. The
    //     operator needs the detail; the teacher must never see it, so always
    //     the generic line. Surfacing "Internal database failure" here is the
    //     regression the friendly-error contract exists to prevent.
    if (status === 503) {
      const detail = safeDetail(api) || safeDetail(body?.detail)
      const message = detail && !INTERNAL_MARKERS.test(detail)
        ? detail
        : FRIENDLY_MESSAGES.server
      return { ...base, category: 'server', message, canRetry: true, showBanner: true }
    }
    return {
      ...base,
      category: 'server',
      message: FRIENDLY_MESSAGES.server,
      canRetry: true,
      showBanner: false,
    }
  }

  const detail = safeDetail(error)
  return {
    ...base,
    category: 'unknown',
    message: detail || FRIENDLY_MESSAGES.unknown,
    canRetry: true,
    showBanner: false,
  }
}

export interface ToastLikeOptions {
  title?: string
  description?: string
  variant?: 'default' | 'destructive' | 'success' | 'info' | 'warning' | 'error'
  duration?: number | null
  action?: { label: string; onClick: () => void }
}

const TOAST_TITLES: Partial<Record<ErrorCategory, string>> = {
  auth: 'Sign in required',
  permission: 'Permission denied',
  entitlement: 'Plan upgrade required',
  validation: 'Check these details',
  not_found: 'Not found',
  conflict: 'Save conflict',
  too_large: 'File too large',
  unsupported: 'Unsupported file',
  rate_limit: 'Please wait',
  network: 'Connection problem',
  timeout: 'Request timed out',
  maintenance: 'Maintenance in progress',
  server: 'Temporarily unavailable',
  unknown: 'Something went wrong',
}

/** Show a toast for an error. Network/maintenance banners stay page-level. */
export function showErrorToast(
  error: unknown,
  toast: (options: ToastLikeOptions) => void,
  action?: { label: string; onClick: () => void },
) {
  const normalized = normalizeError(error)
  if (normalized.category === 'network' || normalized.category === 'maintenance') {
    return
  }
  toast({
    title: TOAST_TITLES[normalized.category] || 'Something went wrong',
    description: normalized.message,
    variant: normalized.category === 'server' ? 'error' : 'default',
    duration: normalized.category === 'validation' ? 6000 : 8000,
    action,
  })
}
