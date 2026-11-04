// Browser acceptance for the post-payment confirmation states.
// No payment is created: the API responses are deterministic fixtures.
const { chromium } = require('playwright')

const WEB = process.env.TF_WEB_URL || 'http://localhost:3010'
const REF = 'TFM-312e7b80-475e34f2211c0682fa9a'

function purchase(fulfilment, overrides = {}) {
  return {
    reference: REF,
    payment_status: fulfilment === 'payment_pending' ? 'pending' : 'success',
    fulfilment_status: fulfilment,
    package: { slug: 'flexible-credit-pack', name: 'Flexible Credit Pack', credits: 20 },
    amount_pesewas: 1200,
    currency: 'GHS',
    paid_at: '2026-11-04T17:32:36Z',
    channel: 'mobile_money',
    credits_granted: fulfilment === 'activated' ? 20 : 0,
    credit_balance: { total: fulfilment === 'activated' ? 20 : 0 },
    licence: { key: 'TF-HIDDEN-KEY', status: fulfilment === 'activated' ? 'active' : 'pending' },
    next_action: '',
    ...overrides,
  }
}

async function scenario(browser, name, fixture, { verifyStatus = 200 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await ctx.addInitScript(() => {
    sessionStorage.setItem('teachflow_token', 'ui-test-token')
    sessionStorage.setItem('teachflow_user', JSON.stringify({
      id: 'u1', email: 'teacher@test.invalid', full_name: 'Test Teacher', role: 'teacher',
    }))
  })
  const page = await ctx.newPage()
  await page.route('**/api/paystack/verify/**', async (route) => {
    if (verifyStatus === 200) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) })
    }
    return route.fulfill({
      status: verifyStatus,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Payment has not been confirmed yet.' }),
    })
  })
  await page.route('**/api/paystack/charge/status/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }))
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        id: 'u1', email: 'teacher@test.invalid', full_name: 'Test Teacher', role: 'teacher',
      }),
    }))

  await page.goto(`${WEB}/payments/callback?reference=${REF}`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-payment-result]').waitFor({ timeout: 30000 })
  await page.waitForTimeout(500)
  const body = await page.locator('body').innerText()
  const keyInputs = await page.locator('#licence-redeem-key').count()
  const keyVisible = body.includes('TF-HIDDEN-KEY')
  if (keyInputs !== 0) throw new Error(`${name}: licence input is still present`)
  if (keyVisible) throw new Error(`${name}: licence key is exposed`)
  await page.screenshot({ path: `e2e/purchase-confirmation-${name}.png`, fullPage: true })
  await ctx.close()
  return body
}

;(async () => {
  const browser = await chromium.launch()
  try {
    const activated = await scenario(browser, 'activated',
      { purchase: purchase('activated') })
    if (!/Purchase activated/i.test(activated)) throw new Error('activated headline missing')
    if (!/Flexible Credit Pack/.test(activated)) throw new Error('package name missing')
    if (!/20/.test(activated)) throw new Error('credits missing')
    if (!/do not need to copy or enter a licence key/i.test(activated)) {
      throw new Error('automatic-licence explanation missing')
    }

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
    console.log('PASS activated confirmation shows package/credits and no key entry')
    console.log('PASS needs-attention confirmation tells teacher not to pay again')
    console.log('PASS pending confirmation explains OTP vs mobile-money approval')
  } finally {
    await browser.close()
  }
})().catch((err) => { console.error('FAIL', err.message); process.exit(1) })
