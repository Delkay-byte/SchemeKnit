// Browser acceptance for the post-payment confirmation and the automatic
// package purchase journey. No payment is created: every Paystack response is
// a deterministic synthetic fixture and the provider is never called.
const { chromium } = require('playwright')

const WEB = process.env.UX_WEB_URL || process.env.TF_WEB_URL || 'http://127.0.0.1:3100'
const REF = 'TFM-312e7b80-475e34f2211c0682fa9a'
const PACKAGE_NAME = 'Flexible Credit Pack'

function purchase(fulfilment, overrides = {}) {
  return {
    reference: REF,
    payment_status: fulfilment === 'payment_pending' ? 'pending'
      : fulfilment === 'payment_failed' ? 'failed' : 'success',
    fulfilment_status: fulfilment,
    package: {
      slug: 'flexible-credit-pack',
      name: PACKAGE_NAME,
      credits: 20,
      kind: 'flexible',
    },
    amount_pesewas: 1200,
    currency: 'GHS',
    paid_at: '2026-11-04T17:32:36Z',
    channel: 'mobile_money',
    credits_granted: fulfilment === 'activated' ? 20 : 0,
    credits_used: 0,
    credits_remaining: fulfilment === 'activated' ? 20 : 0,
    credit_balance: { total: fulfilment === 'activated' ? 20 : 0 },
    licence: { key: 'TF-HIDDEN-KEY', status: fulfilment === 'activated' ? 'active' : 'pending' },
    next_action: '',
    ...overrides,
  }
}

const CATALOGUE = {
  currency: 'GHS',
  payment_methods: ['bank_transfer', 'mobile_money'],
  plans: [{
    slug: 'flexible-credit-pack',
    name: PACKAGE_NAME,
    description: 'Buy 20 indicator-level lesson plans.',
    price_pesewas: 1200,
    price_ghs: 12,
    currency: 'GHS',
    interval: 'one_time',
    duration_days: 0,
    credits: 20,
    credit_validity_days: null,
    package_kind: 'flexible',
    validity_label: 'Credits do not expire',
    payment_terms: 'One-time prepaid payment. No automatic renewal.',
    features: [],
    active: true,
  }],
}

const CREDITS = {
  free: {
    limit: 2, used: 0, remaining: 2, period_key: '2026-11',
    period_type: 'calendar_month', resets: '1st of each month (Africa/Accra)',
    rollover: false,
  },
  purchased: 20,
  package: 0,
  referral: 0,
  packages: [],
  purchased_packages: [{
    slug: 'flexible-credit-pack', label: PACKAGE_NAME, kind: 'flexible',
    granted: 20, used: 0, remaining: 20, expires_at: null,
    granted_at: '2026-11-04T17:32:36Z', reference: REF,
  }],
  expired_packages: [],
  total: 22,
  spending_order: ['free', 'package', 'referral', 'purchased'],
  unit: 'indicator_level_lesson_plan',
}

const PLAN = {
  source: 'individual',
  edition: 'teacher',
  plan: 'PRO',
  plan_name: 'Teacher Pro',
  status: 'active',
  plan_source: 'paystack',
  credits: CREDITS,
  active_package: {
    slug: 'flexible-credit-pack',
    name: PACKAGE_NAME,
    kind: 'flexible',
    credits_granted: 20,
    credits_used: 0,
    credits_remaining: 20,
    paid_at: '2026-11-04T17:32:36Z',
    amount_pesewas: 1200,
    payment_method: 'mobile_money',
    channel: 'mobile_money',
    fulfilment_status: 'activated',
    entitlement_status: 'active',
    expires_at: null,
    reference: REF,
  },
}

function subscriptionFixture() {
  return {
    subscription: null,
    plan: null,
    licence: { key: '', status: 'active', expires_at: null },
    credits: CREDITS,
    customer: { email: 'teacher@test.invalid', name: 'Test Teacher' },
    last_purchase: purchase('activated'),
    pending_payment: null,
    payments: [{
      reference: REF,
      status: 'success',
      amount_pesewas: 1200,
      currency: 'GHS',
      payment_method: 'mobile_money',
      plan_id: 'p-flex',
      plan_name: PACKAGE_NAME,
      created_at: '2026-11-04T17:32:36Z',
      paid_at: '2026-11-04T17:32:36Z',
      credits_granted: 20,
      fulfilment_status: 'activated',
    }],
  }
}

async function json(route, status, body) {
  await route.fulfill({
    status, contentType: 'application/json', body: JSON.stringify(body),
  })
}

async function newContext(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await ctx.addInitScript(() => {
    sessionStorage.setItem('teachflow_token', 'ui-test-token')
    sessionStorage.setItem('teachflow_user', JSON.stringify({
      id: 'u1', email: 'teacher@test.invalid', full_name: 'Test Teacher', role: 'teacher',
    }))
  })
  return ctx
}

async function mockAccount(page) {
  await page.route('**/api/auth/me', (route) => json(route, 200, {
    id: 'u1', email: 'teacher@test.invalid', full_name: 'Test Teacher', role: 'teacher',
  }))
  await page.route('**/api/auth/my-plan', (route) => json(route, 200, PLAN))
  await page.route('**/api/paystack/credits', (route) => json(route, 200, CREDITS))
  await page.route('**/api/paystack/me', (route) => json(route, 200, subscriptionFixture()))
  await page.route('**/api/paystack/catalogue', (route) => json(route, 200, CATALOGUE))
  await page.route('**/api/documents/**', (route) => json(route, 200, { schemes: [] }))
  await page.route('**/api/documents/', (route) => json(route, 200, { schemes: [] }))
  await page.route('**/api/referrals/me', (route) => json(route, 200, {
    link_path: '/register?ref=ui-test', registered: 0, qualifying: 0,
    credits_earned: 0, reward: { referrer: 3, referred: 2 },
  }))
}

async function scenario(browser, name, fixture, { verifyStatus = 200 } = {}) {
  const ctx = await newContext(browser)
  const page = await ctx.newPage()
  await mockAccount(page)
  await page.route('**/api/paystack/verify/**', (route) => {
    if (verifyStatus === 200) {
      return json(route, 200, fixture)
    }
    return json(route, verifyStatus, { detail: 'Payment has not been confirmed yet.' })
  })
  await page.route('**/api/paystack/charge/status/**', (route) =>
    json(route, 200, { purchase: fixture.purchase || fixture }))

  await page.goto(`${WEB}/payments/callback?reference=${REF}`, { waitUntil: 'domcontentloaded' })
  const expectedPhase = (fixture.purchase || fixture).fulfilment_status || 'payment_pending'
  await page.locator(`[data-payment-result="${expectedPhase}"]`).waitFor({ timeout: 30000 })
  await page.waitForTimeout(100)
  const body = await page.locator('body').innerText()
  const keyInputs = await page.locator('#licence-redeem-key').count()
  const keyVisible = body.includes('TF-HIDDEN-KEY')
  if (keyInputs !== 0) throw new Error(`${name}: licence input is still present`)
  if (keyVisible) throw new Error(`${name}: licence key is exposed`)
  await ctx.close()
  return body
}

async function purchaseJourney(browser) {
  const ctx = await newContext(browser)
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))
  await mockAccount(page)
  await page.route('**/api/paystack/momo/charge', (route) => json(route, 200, {
    reference: REF,
    status: 'pending',
    charge_status: 'pay_offline',
    display_text: 'Please complete authorization process on your mobile phone',
    payment_method: 'mobile_money',
    payment_details: {},
    plan: CATALOGUE.plans[0],
  }))
  await page.route('**/api/paystack/verify/**', (route) => json(route, 200, {
    status: 'success', reference: REF, purchase: purchase('activated'),
  }))

  // 1-5. Catalogue, select the Flexible Credit Pack, start checkout.
  await page.goto(`${WEB}/upgrade`, { waitUntil: 'domcontentloaded' })
  const pack = page.locator('[data-package="flexible-credit-pack"]')
  await pack.waitFor({ timeout: 30000 })
  const packText = await pack.innerText()
  if (!packText.includes(PACKAGE_NAME)) throw new Error('catalogue package name missing')
  if (!packText.includes('GH₵12.00')) throw new Error('catalogue price missing')
  await pack.click()
  await page.locator('[data-method="mobile_money"]').click()
  await page.locator('[data-momo-provider]').selectOption('telecel')
  await page.locator('[data-momo-phone]').fill('0201234567')
  await page.locator('[data-start-payment]').click()

  // 6. Accurate payment-processing feedback from the synthetic provider.
  await page.locator('[data-payment-waiting]').waitFor({ timeout: 15000 })
  const waitingText = await page.locator('[data-payment-waiting]').innerText()
  if (!/Check your phone/i.test(waitingText)) throw new Error('processing feedback missing')
  if (/Payment was not completed/i.test(waitingText)) throw new Error('pending shown as failed')

  // 7-10. Verified payment + automatic fulfilment, credits and balance.
  await page.goto(`${WEB}/payments/callback?reference=${REF}`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-payment-result="activated"]').waitFor({ timeout: 30000 })
  const callbackText = await page.locator('[data-payment-result]').innerText()
  if (!/Purchase activated/i.test(callbackText)) throw new Error('activation headline missing')
  if (!callbackText.includes(PACKAGE_NAME)) throw new Error('confirmation package name missing')
  if (!/Credits activated\s*20/i.test(callbackText)) throw new Error('granted credits missing')
  if (!/Current credit balance\s*20/i.test(callbackText)) throw new Error('balance missing')
  if (!/do not need to copy or enter a licence key/i.test(callbackText)) {
    throw new Error('automatic-licence explanation missing')
  }
  if (await page.locator('#licence-redeem-key').count()) {
    throw new Error('licence key entry present after purchase')
  }

  // 11-13. Dashboard and purchase history keep the same entitlement.
  await page.goto(`${WEB}/dashboard`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-active-package="flexible-credit-pack"]').waitFor({ timeout: 30000 })
  const dashboardText = await page.locator('[data-active-package="flexible-credit-pack"]').innerText()
  if (!dashboardText.includes(PACKAGE_NAME)) throw new Error('dashboard package name missing')
  if (!/never expire/i.test(dashboardText)) throw new Error('flexible expiry wording missing')
  if (!dashboardText.includes('20')) throw new Error('dashboard credits missing')
  await page.locator('[data-purchased-packages]').waitFor({ timeout: 15000 })
  const creditsText = await page.locator('[data-dashboard-credits]').innerText()
  if (!/20 of 20 credits remaining/.test(creditsText)) throw new Error('dashboard balance missing')
  if (/expires\s+\d/.test(creditsText) && /Flexible Credit Pack/.test(creditsText)) {
    throw new Error('flexible pack incorrectly shown with an expiry')
  }

  await page.goto(`${WEB}/subscription`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'Purchase history' }).waitFor({ timeout: 30000 })
  const historyText = await page.locator('body').innerText()
  if (!historyText.includes(REF)) throw new Error('purchase history reference missing')
  if (!historyText.includes(PACKAGE_NAME)) throw new Error('purchase history package missing')
  if (!historyText.includes('20 credits granted')) throw new Error('purchase history grant missing')
  if (!/No expiry on your flexible credit pack/i.test(historyText)) {
    throw new Error('flexible licence incorrectly shown with expiry')
  }

  // 14. A refresh retains the correct entitlement.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: 'Purchase history' }).waitFor({ timeout: 30000 })
  if (!(await page.locator('body').innerText()).includes(PACKAGE_NAME)) {
    throw new Error('entitlement lost after refresh')
  }

  // 15. No licence key was ever required.
  if (await page.locator('#licence-redeem-key').count()) {
    throw new Error('licence key entry present on subscription page')
  }
  if (errors.length) throw new Error(`uncaught page errors: ${errors.join(' | ')}`)
  await ctx.close()
}

;(async () => {
  const browser = await chromium.launch()
  try {
    const activated = await scenario(browser, 'activated', { purchase: purchase('activated') })
    if (!/Purchase activated/i.test(activated)) throw new Error('activated headline missing')
    if (!activated.includes(PACKAGE_NAME)) throw new Error('package name missing')
    if (!/Credits activated\s*20/i.test(activated)) throw new Error('credits missing')

    const attention = await scenario(browser, 'attention',
      { purchase: purchase('needs_attention') })
    if (!/activation needs attention/i.test(attention)) throw new Error('attention state missing')
    if (!/Do not pay again/i.test(attention)) throw new Error('no-pay-again guidance missing')

    const pending = await scenario(browser, 'pending',
      { purchase: purchase('payment_pending') }, { verifyStatus: 402 })
    if (!/Payment pending/i.test(pending)) throw new Error('pending state missing')
    if (!/OTP alone does not complete the purchase/i.test(pending)) {
      throw new Error('OTP/PIN guidance missing')
    }

    const failed = await scenario(browser, 'failed', {
      purchase: purchase('payment_failed', {
        payment_status: 'failed', credits_granted: 0,
        credit_balance: { total: 0 },
      }),
    })
    if (!/Payment was not completed/i.test(failed)) throw new Error('failed state missing')
    if (!/No credits were issued/i.test(failed)) throw new Error('failed-credit guidance missing')

    await purchaseJourney(browser)
    console.log('PASS activated confirmation shows package/credits and no key entry')
    console.log('PASS needs-attention confirmation tells teacher not to pay again')
    console.log('PASS pending confirmation explains OTP vs mobile-money approval')
    console.log('PASS failed confirmation says no credits were issued')
    console.log('PASS full flexible-pack purchase journey activates automatically')
  } finally {
    await browser.close()
  }
})().catch((err) => { console.error('FAIL', err.message); process.exit(1) })
