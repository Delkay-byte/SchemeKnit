/**
 * Teacher-safe AI feedback (PART H/I/J/AD).
 *
 * Single presentation layer for every AI suggestion failure. The backend
 * returns a stable `code` plus a raw `diagnostic` (LIVE_ERROR, rate_limit,
 * malformed_json, HTTP status, exception text). NONE of that may reach the
 * teacher: this module maps it to calm, actionable copy that always states
 * (1) AI did not produce a usable suggestion, (2) existing content is safe,
 * (3) the teacher can continue manually, (4) they may retry later.
 */

import type { ApiError } from './api'

export interface AiFailure {
  /** Calm, teacher-facing explanation. Never contains provider internals. */
  message: string
  /** Whether the teacher can reasonably try the same action again later. */
  canRetry: boolean
}

const GENERIC: AiFailure = {
  message:
    'AI suggestion unavailable right now. Your existing content was preserved. ' +
    'You can edit it manually or try again later.',
  canRetry: true,
}

/** Stable backend codes → teacher-safe copy. */
const BY_CODE: Record<string, AiFailure> = {
  AI_UNAVAILABLE: {
    message:
      'AI suggestion is currently unavailable. Your existing content was preserved. ' +
      'You can edit it manually or try again later.',
    canRetry: true,
  },
  AI_RATE_LIMITED: {
    message:
      'AI is busy right now. Your existing content was preserved. ' +
      'Please try again in a moment, or edit it manually.',
    canRetry: true,
  },
  AI_NO_SUGGESTION: GENERIC,
}

/**
 * Map any error thrown by an AI call to teacher-safe feedback.
 *
 * Handles both the structured contract (code) and legacy/plain errors without
 * ever echoing raw exception text, provider state codes or HTTP statuses.
 */
export function aiFailure(err: unknown): AiFailure {
  const e = err as ApiError & { name?: string }

  // A genuine network failure is distinguishable and worth its own wording.
  if (e instanceof TypeError && /fetch|network/i.test(e.message || '')) {
    return {
      message:
        "We couldn't reach the server. Your existing content was preserved. " +
        'Check your connection, or edit it manually and try again later.',
      canRetry: true,
    }
  }
  if (e instanceof DOMException && e.name === 'AbortError') {
    return {
      message:
        'The AI suggestion took too long and was cancelled. Your existing content ' +
        'was preserved. You can edit it manually or try again later.',
      canRetry: true,
    }
  }

  const code = e && typeof e === 'object' ? (e as ApiError).code : undefined
  if (code && BY_CODE[code]) return BY_CODE[code]

  return GENERIC
}
