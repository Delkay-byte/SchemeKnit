/**
 * Local form-draft persistence.
 *
 * Drafts are small, structured, user-scoped values kept in localStorage. They
 * are a convenience for interrupted work, never a server backup and never a
 * source of truth. Server-confirmed data always wins.
 *
 * Security rules:
 * - every draft is namespaced by the authenticated user id;
 * - sensitive keys (passwords, tokens, MFA, invite codes, payment credentials)
 *   are stripped before writing;
 * - raw uploaded files are never persisted;
 * - drafts expire after 30 days and are removed when read.
 */

export const DRAFT_SCHEMA_VERSION = 1
export const DRAFT_TTL_MS = 30 * 24 * 60 * 60 * 1000
const DRAFT_PREFIX = 'schemeknit:draft'
const MAX_DRAFT_BYTES = 64 * 1024

export interface DraftIdentity {
  userId: string
  /** Stable workflow/form identifier, e.g. "lesson-config". */
  workflow: string
  /** Resource the draft belongs to, e.g. a scheme or lesson id. */
  resourceId?: string
}

export interface DraftEnvelope<T> extends DraftIdentity {
  schemaVersion: number
  updatedAt: number
  expiresAt: number
  data: T
}

export interface DraftStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
  key?(index: number): string | null
  readonly length?: number
}

export type DraftSaveResult =
  | { ok: true }
  | { ok: false; error: 'unavailable' | 'quota' | 'too-large' | 'invalid' }

const SENSITIVE_KEY_PATTERN =
  /(password|passcode|passwd|token|secret|mfa|recovery|turnstile|invite|activation|api_?key|card_?number|cvv|bank_?account)/i

/** Remove values that must never be written to browser storage. */
export function sanitizeDraftValue<T>(value: T): T {
  return sanitize(value, 0) as T
}

function sanitize(value: unknown, depth: number): unknown {
  if (depth > 8) return undefined
  if (Array.isArray(value)) {
    return value
      .map((item) => sanitize(item, depth + 1))
      .filter((item) => item !== undefined)
  }
  if (value && typeof value === 'object') {
    const result: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (SENSITIVE_KEY_PATTERN.test(key)) continue
      const next = sanitize(item, depth + 1)
      if (next !== undefined) result[key] = next
    }
    return result
  }
  if (typeof value === 'function' || typeof value === 'symbol') return undefined
  return value
}

function defaultStorage(): DraftStorage | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null
    return window.localStorage
  } catch {
    return null
  }
}

export function draftStorageKey(identity: DraftIdentity): string {
  const scope = identity.resourceId ? `:${identity.resourceId}` : ''
  return `${DRAFT_PREFIX}:v${DRAFT_SCHEMA_VERSION}:${identity.userId}:${identity.workflow}${scope}`
}

export function saveDraft<T>(
  identity: DraftIdentity,
  data: T,
  options: { storage?: DraftStorage | null; now?: number } = {},
): DraftSaveResult {
  const storage = options.storage ?? defaultStorage()
  if (!storage) return { ok: false, error: 'unavailable' }
  if (!identity.userId || !identity.workflow) return { ok: false, error: 'invalid' }

  const now = options.now ?? Date.now()
  const envelope: DraftEnvelope<T> = {
    ...identity,
    schemaVersion: DRAFT_SCHEMA_VERSION,
    updatedAt: now,
    expiresAt: now + DRAFT_TTL_MS,
    data: sanitizeDraftValue(data),
  }

  let serialized: string
  try {
    serialized = JSON.stringify(envelope)
  } catch {
    return { ok: false, error: 'invalid' }
  }
  if (serialized.length > MAX_DRAFT_BYTES) {
    return { ok: false, error: 'too-large' }
  }

  try {
    storage.setItem(draftStorageKey(identity), serialized)
    return { ok: true }
  } catch {
    return { ok: false, error: 'quota' }
  }
}

export function readDraft<T>(
  identity: DraftIdentity,
  options: { storage?: DraftStorage | null; now?: number } = {},
): DraftEnvelope<T> | null {
  const storage = options.storage ?? defaultStorage()
  if (!storage) return null

  const key = draftStorageKey(identity)
  let raw: string | null = null
  try {
    raw = storage.getItem(key)
  } catch {
    return null
  }
  if (!raw) return null

  let parsed: DraftEnvelope<T>
  try {
    parsed = JSON.parse(raw) as DraftEnvelope<T>
  } catch {
    removeDraft(identity, { storage })
    return null
  }

  const now = options.now ?? Date.now()
  const invalid =
    !parsed ||
    parsed.schemaVersion !== DRAFT_SCHEMA_VERSION ||
    parsed.userId !== identity.userId ||
    parsed.workflow !== identity.workflow ||
    (parsed.resourceId || '') !== (identity.resourceId || '') ||
    !parsed.expiresAt ||
    parsed.expiresAt <= now

  if (invalid) {
    removeDraft(identity, { storage })
    return null
  }
  return parsed
}

export function removeDraft(
  identity: DraftIdentity,
  options: { storage?: DraftStorage | null } = {},
): void {
  const storage = options.storage ?? defaultStorage()
  if (!storage) return
  try {
    storage.removeItem(draftStorageKey(identity))
  } catch {
    /* storage unavailable: nothing else to do */
  }
}

/** Delete every expired draft for one user. Safe to call on app start. */
export function sweepExpiredDrafts(
  userId: string,
  options: { storage?: DraftStorage | null; now?: number } = {},
): number {
  const storage = options.storage ?? defaultStorage()
  if (!storage || typeof storage.key !== 'function' || !storage.length) return 0

  const now = options.now ?? Date.now()
  const prefix = `${DRAFT_PREFIX}:v${DRAFT_SCHEMA_VERSION}:${userId}:`
  const keys: string[] = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key && key.startsWith(prefix)) keys.push(key)
  }

  let removed = 0
  for (const key of keys) {
    try {
      const raw = storage.getItem(key)
      if (!raw) continue
      const parsed = JSON.parse(raw) as DraftEnvelope<unknown>
      if (!parsed?.expiresAt || parsed.expiresAt <= now) {
        storage.removeItem(key)
        removed += 1
      }
    } catch {
      try {
        storage.removeItem(key)
        removed += 1
      } catch {
        /* ignore */
      }
    }
  }
  return removed
}

/** Milliseconds since the draft was last updated, for "saved 1 minute ago". */
export function draftAgeLabel(updatedAt: number, now = Date.now()): string {
  const seconds = Math.max(0, Math.floor((now - updatedAt) / 1000))
  if (seconds < 10) return 'just now'
  if (seconds < 60) return `${seconds} seconds ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}
