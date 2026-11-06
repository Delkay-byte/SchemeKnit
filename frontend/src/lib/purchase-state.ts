/** Purchase states shown to the teacher.
 *
 * Payment success is NOT the same event as entitlement activation. These
 * mappings keep the UI honest when Paystack has confirmed a charge but the
 * licence/credits are still being completed.
 */

export type PurchasePhase =
  | 'payment_pending'
  | 'processing'
  | 'activated'
  | 'needs_attention'
  | 'payment_failed'
  | 'payment_reversed'

export interface PurchaseView {
  reference?: string
  payment_status?: string
  fulfilment_status?: string
  package?: { slug?: string; name?: string; credits?: number }
  amount_pesewas?: number
  currency?: string
  paid_at?: string | null
  channel?: string
  credits_granted?: number
  credit_balance?: { total?: number; purchased?: number; package?: number }
  licence?: { key?: string; status?: string; expires_at?: string | null } | null
  notifications?: Record<string, unknown>
  next_action?: string
}

export function purchasePhase(purchase?: PurchaseView | null): PurchasePhase {
  if (!purchase) return 'payment_pending'
  switch (purchase.fulfilment_status) {
    case 'activated':
      return 'activated'
    case 'needs_attention':
      return 'needs_attention'
    case 'payment_failed':
      return 'payment_failed'
    case 'payment_reversed':
      return 'payment_reversed'
    case 'processing':
      return 'processing'
    default:
      return 'payment_pending'
  }
}

export function purchaseHeadline(phase: PurchasePhase): string {
  switch (phase) {
    case 'activated':
      return 'Purchase activated'
    case 'needs_attention':
      return 'Payment received — activation needs attention'
    case 'processing':
      return 'Payment received — activating your purchase'
    case 'payment_failed':
      return 'Payment was not completed'
    case 'payment_reversed':
      return 'Payment was reversed'
    default:
      return 'Payment pending'
  }
}

export function purchaseTone(
  phase: PurchasePhase,
): 'success' | 'warning' | 'danger' | 'info' {
  if (phase === 'activated') return 'success'
  if (phase === 'needs_attention') return 'warning'
  if (phase === 'payment_failed' || phase === 'payment_reversed') return 'danger'
  return 'info'
}

export function isFulfilled(purchase?: PurchaseView | null): boolean {
  return purchasePhase(purchase) === 'activated'
}

export function amountLabel(purchase?: PurchaseView | null): string {
  if (!purchase) return '—'
  const value = Number(purchase.amount_pesewas || 0) / 100
  return `${purchase.currency === 'GHS' || !purchase.currency ? 'GH₵' : purchase.currency + ' '}${value.toFixed(2)}`
}

export function balanceLabel(purchase?: PurchaseView | null): string {
  const total = purchase?.credit_balance?.total
  return typeof total === 'number' ? String(total) : '—'
}
