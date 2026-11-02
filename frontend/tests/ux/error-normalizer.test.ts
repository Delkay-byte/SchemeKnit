import assert from 'node:assert/strict'
import { test } from 'node:test'
import { normalizeError } from '../../src/lib/error-normalizer.ts'

function apiError(message: string, status: number, code?: string, extras: Record<string, unknown> = {}) {
  return Object.assign(new Error(message), { status, code, ...extras })
}

test('network failure gives friendly connection guidance', () => {
  const normalized = normalizeError(new TypeError('Failed to fetch'))
  assert.equal(normalized.category, 'network')
  assert.match(normalized.message, /couldn't connect/i)
  assert.equal(normalized.canRetry, true)
})

test('timeout failure is retryable and friendly', () => {
  const abort = new DOMException('aborted', 'AbortError')
  const normalized = normalizeError(abort)
  assert.equal(normalized.category, 'timeout')
  assert.equal(normalized.canRetry, true)
})

test('401 asks the teacher to sign in again', () => {
  const normalized = normalizeError(apiError('Unauthorized', 401))
  assert.equal(normalized.category, 'auth')
  assert.match(normalized.message, /sign in again/i)
  assert.equal(normalized.canRetry, false)
})

test('403 entitlement is classified before generic permission', () => {
  const normalized = normalizeError(apiError('Generation limit reached', 403, 'entitlement_limit'))
  assert.equal(normalized.category, 'entitlement')
  assert.match(normalized.message, /generation limit/i)
})

test('403 without an entitlement signal stays permission denied', () => {
  const normalized = normalizeError(apiError('Forbidden', 403))
  assert.equal(normalized.category, 'permission')
  assert.match(normalized.message, /permission/i)
})

test('404 is not retried and explains the missing item', () => {
  const normalized = normalizeError(apiError('Lesson not found', 404))
  assert.equal(normalized.category, 'not_found')
  assert.match(normalized.message, /not found/i)
  assert.equal(normalized.canRetry, false)
})

test('409 explains a stale edit', () => {
  const normalized = normalizeError(apiError('Conflict', 409))
  assert.equal(normalized.category, 'conflict')
  assert.match(normalized.message, /changed since you opened it/i)
})

test('413 and 415 explain file problems', () => {
  assert.equal(normalizeError(apiError('Too large', 413)).category, 'too_large')
  assert.equal(normalizeError(apiError('Unsupported', 415)).category, 'unsupported')
})

test('422 uses field-aware curriculum guidance', () => {
  const error = apiError('Validation failed', 422, undefined, {
    details: { errors: [{ field: 'term_start_date' }] },
  })
  const normalized = normalizeError(error)
  assert.equal(normalized.category, 'validation')
  assert.match(normalized.message, /term dates/i)
})

test('429 respects Retry-After seconds', () => {
  const normalized = normalizeError(apiError('Rate limited', 429, undefined, { retryAfter: 30 }))
  assert.equal(normalized.category, 'rate_limit')
  assert.match(normalized.message, /30 seconds/)
  assert.equal(normalized.retryAfterSeconds, 30)
})

test('503 maintenance keeps the server message', () => {
  const error = apiError('Service unavailable', 503, undefined, {
    details: { maintenance: { active: true, message: 'Back at 6pm.' } },
  })
  const normalized = normalizeError(error)
  assert.equal(normalized.category, 'maintenance')
  assert.equal(normalized.message, 'Back at 6pm.')
})

test('500 is retryable and generic', () => {
  const normalized = normalizeError(apiError('Internal Server Error', 500))
  assert.equal(normalized.category, 'server')
  assert.equal(normalized.canRetry, true)
})

test('raw tracebacks never reach the teacher-facing message', () => {
  const normalized = normalizeError(
    apiError('Traceback: psycopg OperationalError SELECT * FROM users', 500),
  )
  assert.doesNotMatch(normalized.message, /traceback|psycopg|select/i)
  assert.match(normalized.technical, /traceback/i)
})

test('Turnstile failures keep their domain guidance', () => {
  const normalized = normalizeError(
    apiError('Bot verification failed. Please complete the challenge again.', 400, 'turnstile_invalid'),
  )
  assert.equal(normalized.category, 'validation')
  assert.match(normalized.message, /verification/i)
})
