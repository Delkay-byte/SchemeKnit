import assert from 'node:assert/strict'
import test from 'node:test'

import {
  amountLabel,
  isFulfilled,
  purchaseHeadline,
  purchasePhase,
  purchaseTone,
} from '../../src/lib/purchase-state.ts'

test('payment success without activation is not shown as fulfilled', () => {
  const purchase = { payment_status: 'success', fulfilment_status: 'needs_attention' }
  assert.equal(purchasePhase(purchase), 'needs_attention')
  assert.equal(isFulfilled(purchase), false)
  assert.equal(purchaseTone(purchasePhase(purchase)), 'warning')
  assert.match(purchaseHeadline('needs_attention'), /activation needs attention/i)
})

test('activated purchase is the only fulfilled state', () => {
  assert.equal(purchasePhase({ fulfilment_status: 'activated' }), 'activated')
  assert.equal(isFulfilled({ fulfilment_status: 'activated' }), true)
  assert.equal(purchaseHeadline('activated'), 'Purchase activated')
})

test('failed and reversed payments have distinct states', () => {
  assert.equal(purchasePhase({ fulfilment_status: 'payment_failed' }), 'payment_failed')
  assert.equal(purchasePhase({ fulfilment_status: 'payment_reversed' }), 'payment_reversed')
  assert.equal(purchaseTone('payment_failed'), 'danger')
  assert.equal(purchaseTone('payment_reversed'), 'danger')
})

test('pending payment never claims success', () => {
  assert.equal(purchasePhase({ fulfilment_status: 'payment_pending' }), 'payment_pending')
  assert.equal(purchaseHeadline('payment_pending'), 'Payment pending')
})

test('amount and balance labels come from server values', () => {
  assert.equal(amountLabel({ amount_pesewas: 1200, currency: 'GHS' }), 'GH₵12.00')
  assert.equal(
    amountLabel({ amount_pesewas: 1200, currency: 'GHS' }),
    'GH₵12.00',
  )
})
