/**
 * Payment checkout acceptance: Ghana Mobile Money authentication states.
 *
 * Paystack responses are mocked at the browser network layer so this test is
 * deterministic and never creates a real charge. It proves the customer sees
 * the correct next action for `send_otp` and `pay_offline`, and that a bad OTP
 * is retryable without being shown as a failed payment.
 *
 * Env: UX_WEB_URL, UX_API_URL, UX_TOKEN, UX_USER
 */
const { chromium } = require('playwright')

const WEB = process.env.UX_WEB_URL || 'http://127.0.0.1:3100'
const TOKEN = process.env.UX_TOKEN || process.env.UX_TEACHER_TOKEN || ''
const USER = JSON.parse(process.env.UX_USER || process.env.UX_TEACHER_USER || '{}')
const results = []

function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

function chargeBody(overrides = {}) {
  return {
    reference: 'TFM-ux-otp-1',
    status: 'pending',
    charge_status: 'send_otp',
    display_text: 'Please enter the OTP sent to your phone',
    payment_method: 'mobile_money',
    payment_details: {},
    plan: null,
    ...overrides,
  }
}

async function json(route, status, body) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function openCheckout(page) {
  await page.goto(`${WEB}/upgrade`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-package]').first().waitFor({ timeout: 30000 })
  const packages = page.locator('[data-package]')
  const count = await packages.count()
  await packages.nth(count > 1 ? 1 : 0).click()
  await page.locator('[data-method="mobile_money"]').click()
  await page.locator('[data-momo-phone]').fill('0241234567')
}

async function sendMomo(page) {
  await page.getByRole('button', { name: /Send Mobile Money request/i }).click()
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await context.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: TOKEN, user: USER })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))

  // ── 1. send_otp shows the form, not a failure ─────────────────────────
  await page.route('**/api/paystack/momo/charge', (route) =>
    json(route, 200, chargeBody()))
  await openCheckout(page)
  await sendMomo(page)

  const otpForm = page.locator('[data-momo-otp]')
  await otpForm.waitFor({ timeout: 15000 }).catch(() => {})
  record('send_otp displays the OTP form', await otpForm.isVisible().catch(() => false))
  record('OTP form shows the payment reference',
    await page.getByText('TFM-ux-otp-1').isVisible().catch(() => false))
  record('send_otp is not shown as a failed payment',
    !(await page.locator('[data-payment-failed]').isVisible().catch(() => false)))

  // ── 2. Invalid OTP is a retryable error, not a failure ────────────────
  await page.route('**/api/paystack/momo/otp', (route) => json(route, 400, {
    detail: 'That one-time password was not accepted. Check the code sent to your phone and try again.',
  }))
  await page.getByLabel('One-time password').fill('000000')
  await page.getByRole('button', { name: 'Submit OTP' }).click()
  await page.getByText(/not accepted/i).waitFor({ timeout: 15000 }).catch(() => {})
  record('invalid OTP shows a retryable error',
    await page.getByText(/not accepted/i).isVisible().catch(() => false))
  record('the OTP form remains after an invalid code',
    await page.locator('[data-momo-otp]').isVisible().catch(() => false))
  record('an invalid OTP is not reported as failed payment',
    !(await page.locator('[data-payment-failed]').isVisible().catch(() => false)))

  // ── 3. OTP accepted → phone authorisation, still not failed ───────────
  await page.unroute('**/api/paystack/momo/otp')
  await page.route('**/api/paystack/momo/otp', (route) => json(route, 200,
    chargeBody({ reference: 'TFM-ux-otp-1', charge_status: 'pending', display_text: '' })))
  await page.getByRole('button', { name: 'Submit OTP' }).click()
  await page.locator('[data-payment-waiting]').waitFor({ timeout: 15000 }).catch(() => {})
  record('accepted OTP moves to phone authorisation',
    await page.locator('[data-payment-waiting]').isVisible().catch(() => false))
  record('pending after OTP is not reported as failed',
    !(await page.locator('[data-payment-failed]').isVisible().catch(() => false)))
  record('pending after OTP explains the phone authorisation',
    await page.getByText(/Check your phone/i).first().isVisible().catch(() => false))

  // ── 4. pay_offline shows display_text + provider guidance, no OTP form ─
  await page.unroute('**/api/paystack/momo/charge')
  await page.route('**/api/paystack/momo/charge', (route) => json(route, 200,
    chargeBody({
      reference: 'TFM-ux-offline-1',
      charge_status: 'pay_offline',
      display_text: 'Please complete authorization process on your mobile phone',
    })))
  await page.goto(`${WEB}/upgrade`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-package]').first().waitFor({ timeout: 30000 })
  const packages = page.locator('[data-package]')
  await packages.nth((await packages.count()) > 1 ? 1 : 0).click()
  await page.locator('[data-method="mobile_money"]').click()
  await page.locator('[data-momo-phone]').fill('0241234567')
  await sendMomo(page)

  await page.locator('[data-payment-stage="pay_offline"]').waitFor({ timeout: 15000 }).catch(() => {})
  record('pay_offline is rendered as its own stage',
    await page.locator('[data-payment-stage="pay_offline"]').isVisible().catch(() => false))
  record('pay_offline shows Paystack display_text',
    await page.getByText(/complete authorization process on your mobile phone/i)
      .first().isVisible().catch(() => false))
  record('pay_offline never shows a website OTP form',
    !(await page.locator('[data-momo-otp]').isVisible().catch(() => false)))
  record('pay_offline warns against entering the MoMo PIN here',
    await page.getByText(/Enter your Mobile Money PIN only in your provider/i)
      .isVisible().catch(() => false))
  record('pay_offline explains where the SMS code belongs',
    await page.getByText(/enter it in the Mobile Money prompt/i)
      .isVisible().catch(() => false))
  record('pay_offline is not reported as failed',
    !(await page.locator('[data-payment-failed]').isVisible().catch(() => false)))

  record('no uncaught page errors', errors.length === 0, errors.join(' | '))
  await browser.close()

  const failed = results.filter((item) => !item.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  process.exit(failed.length ? 1 : 0)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
