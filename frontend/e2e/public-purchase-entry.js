/**
 * Public purchase-entry browser acceptance.
 *
 * Usage: node e2e/public-purchase-entry.js [baseUrl]
 * Requires the built frontend on the given base URL. No payment is started.
 */
const { chromium } = require('playwright')

const BASE = process.argv[2] || 'http://localhost:3000'
let pass = 0
let fail = 0
function log(ok, label, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

const PACKAGE = {
  slug: 'flexible-credit-pack',
  name: 'Flexible Credit Pack',
  price: 'GH₵12.00',
  credits: '20 lesson-plan credits',
  validity: 'Credits do not expire',
}
const NEXT = encodeURIComponent('/upgrade?package=flexible-credit-pack')

async function openModal(page) {
  await page.goto(BASE + '/pricing', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator(`[data-choose-package="${PACKAGE.slug}"]`).last().click()
  const dialog = page.getByRole('dialog')
  await dialog.waitFor({ state: 'visible', timeout: 10000 })
  return dialog
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    for (const [label, viewport] of [
      ['desktop', { width: 1440, height: 900 }],
      ['mobile', { width: 390, height: 844 }],
    ]) {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      const dialog = await openModal(page)
      const text = await dialog.innerText()
      log(text.includes('Almost there! Your package is waiting.'), `${label}: modal heading`)
      log(text.includes(PACKAGE.name), `${label}: selected package name`)
      log(text.includes(PACKAGE.price), `${label}: selected price`)
      log(text.includes(PACKAGE.credits), `${label}: selected credits`)
      log(text.includes(PACKAGE.validity), `${label}: selected validity`)
      log(text.includes('pilot invitation code'), `${label}: invite-only notice`)

      const signup = await dialog.getByRole('link', { name: /create a free teacher account/i }).getAttribute('href')
      const login = await dialog.getByRole('link', { name: /already have an account/i }).getAttribute('href')
      log(signup === `/signup/?next=${NEXT}`, `${label}: signup preserves package`, signup || '')
      log(login === `/login/?next=${NEXT}`, `${label}: login preserves package`, login || '')

      await page.keyboard.press('Escape')
      await dialog.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {})
      log(await page.getByRole('dialog').count() === 0, `${label}: Escape closes`)

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      log(overflow <= 1, `${label}: no horizontal overflow`, String(overflow))
      await context.close()
    }

    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await context.newPage()

    await page.goto(BASE + '/upgrade?package=flexible-credit-pack', { waitUntil: 'domcontentloaded' })
    await page.waitForURL((u) => u.pathname.startsWith('/login'), { timeout: 15000 })
    const redirected = decodeURIComponent(page.url())
    log(redirected.includes('/upgrade') && redirected.includes('package=flexible-credit-pack'), 'direct upgrade redirect preserves package', page.url())

    await page.goto(BASE + '/login?next=' + NEXT, { waitUntil: 'domcontentloaded' })
    const signupHref = await page.getByRole('link', { name: /create teacher account/i }).last().getAttribute('href')
    log(signupHref === `/signup/?next=${NEXT}`, 'login → signup preserves package', signupHref || '')

    await page.goto(BASE + '/signup?next=' + NEXT, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => {
      const link = Array.from(document.querySelectorAll('a')).find((a) => a.textContent?.trim() === 'Sign in')
      return Boolean(link && link.getAttribute('href')?.includes('next='))
    }, { timeout: 10000 })
    const loginHref = await page.getByRole('link', { name: /^sign in$/i }).first().getAttribute('href')
    log(loginHref === `/login/?next=${NEXT}`, 'signup → login preserves package', loginHref || '')

    await page.goto(BASE + '/upgrade?package=not-a-package', { waitUntil: 'domcontentloaded' })
    await page.waitForURL((u) => u.pathname.startsWith('/login'), { timeout: 15000 })
    log(!page.url().includes('not-a-package'), 'invalid package is not preserved', page.url())

    await page.goto(BASE + '/login?next=https%3A%2F%2Fevil.example%2Fupgrade', { waitUntil: 'domcontentloaded' })
    const unsafeSignup = await page.getByRole('link', { name: /create teacher account/i }).last().getAttribute('href')
    log(unsafeSignup === '/signup/', 'external next is rejected', unsafeSignup || '')

    await context.close()
  } catch (err) {
    log(false, 'purchase-entry flow', err.message)
  } finally {
    await browser.close()
  }
  console.log(`\n${pass} passed, ${fail} failed`)
  process.exit(fail ? 1 : 0)
})()
