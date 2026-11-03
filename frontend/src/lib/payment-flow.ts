/**
 * Mobile Money / charge state helpers.
 *
 * Paystack answers a charge with its own status vocabulary
 * (`send_otp`, `pending`, `pay_offline`, `success`, `failed`, `timeout`).
 * These helpers turn that into the states the checkout UI is allowed to show,
 * so `send_otp` can never be mistaken for failure and a pending authorisation
 * is never declared failed early.
 */

export interface ChargeLike {
  status?: string | null
  charge_status?: string | null
  payment_method?: string | null
  payment_details?: Record<string, unknown> | null
  reference?: string | null
}

export type ChargeStage =
  | 'otp'
  | 'bank_transfer'
  | 'awaiting_momo_authorisation'
  | 'pending'
  | 'success'
  | 'failed'

/** Paystack is waiting for the emailed/SMS one-time password. */
export function isOtpRequired(charge: ChargeLike | null | undefined): boolean {
  return charge?.status === 'pending' && charge?.charge_status === 'send_otp'
}

/** A MoMo charge the customer authorises on their own phone. */
export function isAwaitingMomoAuthorisation(
  charge: ChargeLike | null | undefined,
): boolean {
  return Boolean(
    charge && charge.status === 'pending'
    && charge.payment_method === 'mobile_money'
    && charge.charge_status !== 'send_otp',
  )
}

/** A bank-transfer charge that shows the generated account details. */
export function isBankTransferPrompt<T extends ChargeLike>(
  charge: T | null | undefined,
): charge is T & { payment_details: NonNullable<T['payment_details']> } {
  return Boolean(
    charge && charge.status === 'pending'
    && charge.payment_method !== 'mobile_money'
    && charge.payment_details?.account_number,
  )
}

/** Only a confirmed provider outcome is final. `pending` never is. */
export function isFinalFailure(charge: ChargeLike | null | undefined): boolean {
  return charge?.status === 'failed' || charge?.status === 'expired'
}

export function isSuccess(charge: ChargeLike | null | undefined): boolean {
  return charge?.status === 'success'
}

/** Poll only a genuinely pending charge that is not blocked on OTP entry. */
export function shouldPollCharge(charge: ChargeLike | null | undefined): boolean {
  return Boolean(charge && charge.status === 'pending' && !isOtpRequired(charge))
}

/** Paystack asks for at least 10 seconds before the first pending check. */
export const PENDING_CHECK_DELAY_MS = 10_000
export const PENDING_POLL_INTERVAL_MS = 12_000

export function canCheckStatus(
  startedAt: number | null,
  now: number,
  delayMs: number = PENDING_CHECK_DELAY_MS,
): boolean {
  if (startedAt == null) return false
  return now - startedAt >= delayMs
}

export function chargeStage(charge: ChargeLike | null | undefined): ChargeStage {
  if (isSuccess(charge)) return 'success'
  if (isFinalFailure(charge)) return 'failed'
  if (isOtpRequired(charge)) return 'otp'
  if (isAwaitingMomoAuthorisation(charge)) return 'awaiting_momo_authorisation'
  if (isBankTransferPrompt(charge)) return 'bank_transfer'
  return 'pending'
}

/** Customer-facing copy for each stage (no premature failure wording). */
export function chargeStageMessage(stage: ChargeStage): string {
  switch (stage) {
    case 'otp':
      return 'Enter the one-time password sent to your phone to continue.'
    case 'awaiting_momo_authorisation':
      return 'Your Mobile Money request is being processed. Check your phone and complete the authorization using your Mobile Money PIN.'
    case 'bank_transfer':
      return 'Waiting for your transfer.'
    case 'pending':
      return 'We are waiting for confirmation from your Mobile Money provider. Your payment has not yet been confirmed.'
    case 'success':
      return 'Payment successful. Your package is now active.'
    case 'failed':
      return 'Payment was not completed. No credits were issued.'
  }
}

/** Only run the provider-dependent actions for the right stage. */
export function canSubmitOtp(charge: ChargeLike | null | undefined, otp: string): boolean {
  const digits = (otp || '').replace(/\D/g, '')
  return isOtpRequired(charge) && digits.length >= 4 && digits.length <= 8
}
