/**
 * Explicit-empty overrides for profile prefill.
 *
 * The backend stores an intentionally blank lesson-config field as `null`,
 * the same as a field that was never configured. This user-scoped, versioned
 * local record remembers deliberate clears so a profile default is not applied
 * again on the next open. It is a UI preference, not server data.
 */

export const PREFILL_OVERRIDE_VERSION = 1
const PREFIX = 'schemeknit:prefill-overrides'

export interface PrefillOverrideIdentity {
  userId: string
  workflow: string
  resourceId?: string
}

export interface PrefillOverrideRecord {
  version: number
  cleared: string[]
  updatedAt: number
}

export interface OverrideStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

function defaultStorage(): OverrideStorage | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null
    return window.localStorage
  } catch {
    return null
  }
}

export function prefillOverrideKey(identity: PrefillOverrideIdentity): string {
  const resource = identity.resourceId ? `:${identity.resourceId}` : ''
  return `${PREFIX}:v${PREFILL_OVERRIDE_VERSION}:${identity.userId}:${identity.workflow}${resource}`
}

export function readClearedFields(
  identity: PrefillOverrideIdentity,
  options: { storage?: OverrideStorage | null } = {},
): Set<string> {
  const storage = options.storage ?? defaultStorage()
  if (!storage || !identity.userId) return new Set()
  try {
    const raw = storage.getItem(prefillOverrideKey(identity))
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as PrefillOverrideRecord
    if (parsed?.version !== PREFILL_OVERRIDE_VERSION || !Array.isArray(parsed.cleared)) {
      return new Set()
    }
    return new Set(parsed.cleared.filter((field) => typeof field === 'string'))
  } catch {
    return new Set()
  }
}

export function setFieldCleared(
  identity: PrefillOverrideIdentity,
  field: string,
  cleared: boolean,
  options: { storage?: OverrideStorage | null; now?: number } = {},
): void {
  const storage = options.storage ?? defaultStorage()
  if (!storage || !identity.userId || !field) return
  const current = readClearedFields(identity, { storage })
  if (cleared) current.add(field)
  else current.delete(field)

  if (current.size === 0) {
    try {
      storage.removeItem(prefillOverrideKey(identity))
    } catch {
      /* ignore */
    }
    return
  }

  try {
    const record: PrefillOverrideRecord = {
      version: PREFILL_OVERRIDE_VERSION,
      cleared: Array.from(current).sort(),
      updatedAt: options.now ?? Date.now(),
    }
    storage.setItem(prefillOverrideKey(identity), JSON.stringify(record))
  } catch {
    /* storage unavailable: prefill remains best-effort */
  }
}

export function clearPrefillOverrides(
  identity: PrefillOverrideIdentity,
  options: { storage?: OverrideStorage | null } = {},
): void {
  const storage = options.storage ?? defaultStorage()
  if (!storage) return
  try {
    storage.removeItem(prefillOverrideKey(identity))
  } catch {
    /* ignore */
  }
}
