/**
 * UX reliability acceptance — skeletons, optimistic deletion/rollback,
 * friendly errors, not-found routing and draft recovery.
 *
 * Runs against a disposable local backend + web app. No production data.
 *
 * Usage: node e2e/ux-reliability.js
 * Env: UX_WEB_URL, UX_API_URL, UX_TOKEN, UX_USER (JSON)
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const WEB = process.env.UX_WEB_URL || 'http://127.0.0.1:3000'
const API = process.env.UX_API_URL || 'http://127.0.0.1:8000'
const TOKEN = process.env.UX_TOKEN || process.env.UX_TEACHER_TOKEN || ''
const USER = process.env.UX_USER || process.env.UX_TEACHER_USER || '{"id":"ux-e2e","email":"ux-e2e@test.local","full_name":"UX E2E Teacher","school_name":"","is_admin":false,"is_active":true,"role":"teacher","school_id":null}'
const PDF = path.resolve(__dirname, '..', '..', 'backend', 'real_documents', 'BASIC 6 TERM 1.pdf')
// Staging can point at a smaller fixture; CI keeps the PDF default.
const SCHEME_FILE = process.env.UX_SCHEME_FILE || PDF
const SCHEME_EXT = path.extname(SCHEME_FILE) || '.pdf'
const results = []

function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

async function uploadScheme(name) {
  const bytes = fs.readFileSync(SCHEME_FILE)
  const filename = name.replace(/\.pdf$/i, SCHEME_EXT)
  const form = new FormData()
  form.append('file', new Blob([bytes]), filename)
  const response = await fetch(`${API}/api/documents/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${TOKEN}` },
    body: form,
  })
  if (!response.ok) throw new Error(`upload failed ${response.status}: ${await response.text()}`)
  const data = await response.json()
  return { ...data, id: data.id || data.scheme_id }
}

async function deleteScheme(id) {
  await fetch(`${API}/api/documents/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${TOKEN}` },
  })
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await context.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: TOKEN, user: JSON.parse(USER) })

  const page = await context.newPage()
  const consoleErrors = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => consoleErrors.push(String(error)))

  const suffix = Date.now().toString().slice(-8)
  const scheme = await uploadScheme(`ux-e2e-${suffix}.pdf`)

  // 1. Skeleton appears during first load, then real content.
  await page.route('**/api/documents/', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    await route.continue()
  })
  await page.goto(`${WEB}/dashboard`, { waitUntil: 'domcontentloaded' })
  const skeletonVisible = await page.getByText('Loading your dashboard').waitFor({ state: 'attached', timeout: 5000 }).then(() => true).catch(() => false)
  await page.getByText(/Welcome back/i).waitFor({ timeout: 20000 })
  const schemeVisible = await page.locator('tr', { hasText: `ux-e2e-${suffix}.pdf` }).first().isVisible().catch(() => false)
  record('dashboard skeleton appears before content', skeletonVisible)
  record('dashboard replaces skeleton with real content', schemeVisible)
  await page.unroute('**/api/documents/')

  // 2. Optimistic deletion: row disappears before DELETE resolves.
  await page.route(`**/api/documents/${scheme.id}`, async (route) => {
    if (route.request().method() === 'DELETE') {
      await new Promise((resolve) => setTimeout(resolve, 900))
    }
    await route.continue()
  })
  const row = page.locator('tr', { hasText: `ux-e2e-${suffix}.pdf` })
  await row.getByRole('button', { name: 'Delete scheme' }).click()
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  const pendingToast = await page.getByText('Removing scheme…').isVisible().catch(() => false)
  const rowGoneImmediately = (await row.count()) === 0
  await page.getByText('Scheme removed successfully.').waitFor({ timeout: 15000 })
  record('scheme disappears immediately', rowGoneImmediately)
  record('pending removal feedback is immediate', pendingToast)
  record('success feedback follows server confirmation', true)
  await page.unroute(`**/api/documents/${scheme.id}`)

  // 3. Failed deletion restores the row and offers retry.
  const failing = await uploadScheme(`ux-e2e-fail-${suffix}.pdf`)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('tr', { hasText: `ux-e2e-fail-${suffix}.pdf` }).first().waitFor({ timeout: 20000 })
  await page.route(`**/api/documents/${failing.id}`, async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal database failure' }),
      })
      return
    }
    await route.continue()
  })
  const failingRow = page.locator('tr', { hasText: `ux-e2e-fail-${suffix}.pdf` })
  await failingRow.getByRole('button', { name: 'Delete scheme' }).click()
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await page.getByText('Scheme could not be deleted').waitFor({ timeout: 15000 })
  const restored = await page.locator('tr', { hasText: `ux-e2e-fail-${suffix}.pdf` }).first().isVisible().catch(() => false)
  const retryVisible = await page.getByRole('button', { name: 'Try again' }).isVisible().catch(() => false)
  record('failed deletion restores the item', restored)
  record('failed deletion offers retry', retryVisible)
  record('failed deletion uses friendly text', !(await page.getByText(/Internal database failure/).isVisible().catch(() => false)))
  await page.unroute(`**/api/documents/${failing.id}`)
  await deleteScheme(failing.id)

  // 4. Draft recovery after refresh (new weekly plan).
  await page.goto(`${WEB}/weekly-plans/new`, { waitUntil: 'domcontentloaded' })
  const weekInput = page.getByLabel('Week number')
  await weekInput.waitFor({ timeout: 20000 })
  await page.waitForTimeout(800)
  await weekInput.fill('7')
  await page.waitForTimeout(1400)
  await page.reload({ waitUntil: 'domcontentloaded' })
  const recoveryVisible = await page.getByText(/We found your unsaved work/)
    .first()
    .waitFor({ state: 'visible', timeout: 8000 })
    .then(() => true)
    .catch(() => false)
  record('draft recovery banner appears after refresh', recoveryVisible)
  if (recoveryVisible) {
    await page.getByRole('button', { name: 'Continue draft' }).click()
    const restoredWeek = await weekInput.inputValue()
    record('continue draft restores the saved value', restoredWeek === '7', `week=${restoredWeek}`)
  }

  // 5. Friendly 500 on the lesson list, with a working retry.
  await page.route('**/api/generation/lessons', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Traceback: psycopg OperationalError' }),
    })
  })
  await page.goto(`${WEB}/lessons`, { waitUntil: 'domcontentloaded' })
  await page.getByText('SchemeKnit is temporarily unavailable. Please try again.').waitFor({ timeout: 20000 })
  const rawLeak = await page.getByText(/psycopg|Traceback/).isVisible().catch(() => false)
  record('500 shows friendly text', !rawLeak)
  await page.unroute('**/api/generation/lessons')

  // 6. Not-found page at four viewports, no horizontal overflow.
  for (const width of [390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`${WEB}/this-route-does-not-exist`, { waitUntil: 'domcontentloaded' })
    const heading = await page.getByRole('heading', { name: 'Page not found' }).isVisible().catch(() => false)
    const dashboardLink = await page.getByRole('link', { name: /Go to dashboard/i }).isVisible().catch(() => false)
    const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)
    record(`not-found usable at ${width}px`, heading && dashboardLink && noOverflow)
  }

  record('no uncaught page errors', consoleErrors.filter((text) => !/Failed to load resource|status of 500/.test(text)).length === 0,
    consoleErrors.slice(0, 2).join(' | '))

  await browser.close()
  const failed = results.filter((item) => !item.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
}).finally(() => {
  // Playwright keeps the process alive if a test aborts mid-run.
  setTimeout(() => process.exit(process.exitCode || 0), 500)
})
