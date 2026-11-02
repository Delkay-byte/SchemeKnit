/**
 * Optimistic UI helper.
 *
 * Apply the expected change immediately, then reconcile with the server. On
 * failure the caller's rollback restores the exact previous state. This helper
 * is for safe, reversible mutations only — never payments, activation, credits,
 * MFA or other operations that must wait for authoritative confirmation.
 */
export type MutationKind =
  | 'teacher-account-status'
  | 'scheme-delete'
  | 'holiday-delete'
  | 'lesson-save'
  | 'weekly-plan-save'
  | 'profile-save'
  | 'licence-activation'
  | 'payment'
  | 'credit-change'
  | 'mfa'
  | 'auth'
  | 'turnstile'

/**
 * Only reversible, ordinary account/content mutations may be shown as done
 * before the server confirms. Licence/payment/credit/MFA/auth operations must
 * wait for the authoritative response.
 */
const SERVER_CONFIRMED_ONLY: ReadonlySet<MutationKind> = new Set([
  'licence-activation',
  'payment',
  'credit-change',
  'mfa',
  'auth',
  'turnstile',
])

export function canApplyOptimistically(kind: MutationKind): boolean {
  return !SERVER_CONFIRMED_ONLY.has(kind)
}

export interface OptimisticRun<T> {
  apply: () => void
  rollback: () => void
  request: () => Promise<T>
  onSuccess?: (result: T) => void
  onError?: (error: unknown) => void
}

export async function runOptimistic<T>({
  apply,
  rollback,
  request,
  onSuccess,
  onError,
}: OptimisticRun<T>): Promise<T> {
  apply()
  try {
    const result = await request()
    onSuccess?.(result)
    return result
  } catch (error) {
    rollback()
    onError?.(error)
    throw error
  }
}

/** Re-insert an item at its previous index without mutating the source array. */
export function restoreAt<T>(items: T[], item: T, index: number): T[] {
  const next = items.slice()
  const safeIndex = Math.max(0, Math.min(index, next.length))
  next.splice(safeIndex, 0, item)
  return next
}
