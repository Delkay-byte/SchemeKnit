/**
 * Turnstile registration + challenge-triggered login — browser acceptance.
 *
 * Requires a backend started with the documented Cloudflare TEST keys:
 *   TURNSTILE_ENABLED=true
 *   TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
 *   TURNSTILE_SITE_KEY=1x00000000000000000000AA
 *   TURNSTILE_ALLOWED_HOSTNAMES=localhost,127.0.0.1
 * and a frontend built with NEXT_PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA.
 *
 * Usage: node e2e/turnstile-auth.js [baseUrl] [apiUrl]
 * Never uses a production secret.
 */
const { chromium } = require('playwright')

const BASE = process.argv[2] || 'http://localhost:3000'
const API = process.argv[3] || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
const PASSWORD = 'Turnstile#2026'

let pass = 0
let fail = 0
function log(ok, label, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function waitForVerification(page) {
  await page.getByText('Verification complete.', { exact: false })
    .waitFor({ state: 'visible', timeout: 30000 })
}

async function register(page, email) {
  await page.goto(BASE + '/signup', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.locator('#signup-name').fill('Turnstile Acceptance')
  await page.locator('#signup-email').fill(email)
  await page.locator('#signup-password').fill(PASSWORD)
  await page.locator('#signup-confirm').fill(PASSWORD)
  await waitForVerification(page)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL((u) => u.pathname.startsWith('/dashboard'), { timeout: 30000 })
}

async function forceFailedLogins(email) {
  for (let i = 0; i < 3; i++) {
    await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: 'wrong-password', entry: 'teacher' }),
    })
  }
}

async function challengedLogin(page, email) {
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  // The backend returns 428 on the first attempt; the widget then appears.
  await waitForVerification(page)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    for (const [label, viewport] of [
      ['desktop', { width: 1440, height: 900 }],
      ['mobile', { width: 390, height: 844 }],
    ]) {
      const suffix = `${Date.now()}-${label}`
      const email = `turnstile.${suffix}@schemeknit.test`
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      await register(page, email)
      log(true, `${label}: registration passed with a Turnstile token`)

      await forceFailedLogins(email)
      // A new tab has tab-scoped sessionStorage, so it starts signed out.
      await page.close()
      const loginPage = await context.newPage()
      await challengedLogin(loginPage, email)
      log(true, `${label}: login challenge appeared and verified`)

      await context.close()
    }
  } catch (err) {
    log(false, 'browser acceptance flow', err.message)
  } finally {
    await browser.close()
  }
  console.log(`\n${pass} passed, ${fail} failed`)
  process.exit(fail ? 1 : 0)
})()
