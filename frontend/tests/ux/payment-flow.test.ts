import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  PENDING_CHECK_DELAY_MS,
  canCheckStatus,
  canSubmitOtp,
  chargeStage,
  chargeStageMessage,
  isAwaitingMomoAuthorisation,
  isBankTransferPrompt,
  isFinalFailure,
  isOtpRequired,
  isSuccess,
  shouldPollCharge,
} from '../../src/lib/payment-flow.ts'

test('send_otp shows the OTP form and is never a failed payment', () => {
  const charge = { status: 'pending', charge_status: 'send_otp', payment_method: 'mobile_money' }
  assert.equal(isOtpRequired(charge), true)
  assert.equal(isFinalFailure(charge), false)
  assert.equal(chargeStage(charge), 'otp')
  assert.equal(shouldPollCharge(charge), false)
  assert.match(chargeStageMessage('otp'), /one-time password/i)
})

test('an OTP can only be submitted while the charge awaits it', () => {
  const otpCharge = { status: 'pending', charge_status: 'send_otp', payment_method: 'mobile_money' }
  assert.equal(canSubmitOtp(otpCharge, '123456'), true)
  assert.equal(canSubmitOtp(otpCharge, '123'), false)
  assert.equal(canSubmitOtp(otpCharge, '123456789'), false)
  assert.equal(canSubmitOtp({ ...otpCharge, charge_status: 'pending' }, '123456'), false)
  assert.equal(canSubmitOtp({ ...otpCharge, status: 'success' }, '123456'), false)
})

test('submit_otp returning pending keeps the payment pending and pollable', () => {
  const charge = { status: 'pending', charge_status: 'pending', payment_method: 'mobile_money' }
  assert.equal(isOtpRequired(charge), false)
  assert.equal(isAwaitingMomoAuthorisation(charge), true)
  assert.equal(isFinalFailure(charge), false)
  assert.equal(chargeStage(charge), 'awaiting_momo_authorisation')
  assert.equal(shouldPollCharge(charge), true)
  assert.doesNotMatch(chargeStageMessage('awaiting_momo_authorisation'), /not completed|no credits/i)
})

test('pay_offline MoMo charges are awaiting authorisation, not failures', () => {
  const charge = { status: 'pending', charge_status: 'pay_offline', payment_method: 'mobile_money' }
  assert.equal(isAwaitingMomoAuthorisation(charge), true)
  assert.equal(isFinalFailure(charge), false)
  assert.equal(shouldPollCharge(charge), true)
})

test('pending checks wait at least ten seconds', () => {
  const started = 1_000_000
  assert.equal(canCheckStatus(null, started + 60_000), false)
  assert.equal(canCheckStatus(started, started + PENDING_CHECK_DELAY_MS - 1), false)
  assert.equal(canCheckStatus(started, started + PENDING_CHECK_DELAY_MS), true)
})

test('only confirmed provider outcomes are final', () => {
  assert.equal(isFinalFailure({ status: 'failed' }), true)
  assert.equal(isFinalFailure({ status: 'expired' }), true)
  assert.equal(isFinalFailure({ status: 'pending', charge_status: 'pay_offline' }), false)
  assert.equal(isFinalFailure({ status: 'pending', charge_status: 'send_otp' }), false)
  assert.match(chargeStageMessage('failed'), /No credits were issued/)
})

test('success stops polling and activates the package copy', () => {
  const charge = { status: 'success', charge_status: 'success' }
  assert.equal(isSuccess(charge), true)
  assert.equal(isFinalFailure(charge), false)
  assert.equal(shouldPollCharge(charge), false)
  assert.equal(chargeStage(charge), 'success')
  assert.match(chargeStageMessage('success'), /now active/)
})

test('bank transfers keep their account prompt, not the OTP prompt', () => {
  const charge = {
    status: 'pending',
    charge_status: 'pay_offline',
    payment_method: 'bank_transfer',
    payment_details: { account_number: '1234567890' },
  }
  assert.equal(isBankTransferPrompt(charge), true)
  assert.equal(isOtpRequired(charge), false)
  assert.equal(isAwaitingMomoAuthorisation(charge), false)
  assert.equal(chargeStage(charge), 'bank_transfer')
})

test('a pending network check leaves the stage pending', () => {
  // A temporary failure surfaces as a thrown request; the stored charge stays
  // pending. The stage helpers never turn that into failure.
  const charge = { status: 'pending', charge_status: 'send_otp', payment_method: 'mobile_money' }
  assert.notEqual(chargeStage(charge), 'failed')
  assert.equal(chargeStageMessage('pending'), 'We are waiting for confirmation from your Mobile Money provider. Your payment has not yet been confirmed.')
})
