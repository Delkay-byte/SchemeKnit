/**
 * Administrator teacher account activation/deactivation browser acceptance.
 * Disposable local data only. Licence/payment/licence actions are NOT part of
 * this optimistic path.
 *
 * Env: UX_WEB_URL, UX_API_URL, UX_ADMIN_TOKEN, UX_ADMIN_USER,
 *      UX_ACTIVE_TEACHER_ID, UX_INACTIVE_TEACHER_ID, UX_TEACHER_TOKEN
 */
const { chromium } = require('playwright')

const WEB = process.env.UX_WEB_URL || 'http://127.0.0.1:3100'
const API = process.env.UX_API_URL || 'http://127.0.0.1:8100'
const ADMIN_TOKEN = process.env.UX_ADMIN_TOKEN || ''
const ADMIN_USER = JSON.parse(process.env.UX_ADMIN_USER || '{}')
const ACTIVE_ID = process.env.UX_ACTIVE_TEACHER_ID || ''
const INACTIVE_ID = process.env.UX_INACTIVE_TEACHER_ID || ''
const TEACHER_TOKEN = process.env.UX_TEACHER_TOKEN || ''
const results = []
function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}
async function api(path, token, options = {}) {
  const r = await fetch(`${API}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) },
  })
  return { status: r.status, body: await r.json().catch(() => null) }
}
function userById(users, id) {
  return users.find((user) => user.id === id)
}

async function main() {
  const browser = await chromium.launch()
  const adminContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await adminContext.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: ADMIN_TOKEN, user: ADMIN_USER })
  const page = await adminContext.newPage()

  await page.goto(`${WEB}/school-admin/teachers`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: /Teachers \(/ }).waitFor({ timeout: 30000 })
  await page.getByText('Inactive UX Teacher').waitFor({ timeout: 20000 })

  // Activation with delayed response: optimistic state before confirmation.
  await page.route(`**/api/auth/users/${INACTIVE_ID}/toggle-active`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await route.continue()
  })
  await page.locator('tr', { hasText: 'ux-inactive@test.local' }).getByTitle('Reactivate').click()
  await page.getByRole('button', { name: 'Continue' }).click()
  const optimisticActive = await page.locator('tr', { hasText: 'ux-inactive@test.local' })
    .getByText('active', { exact: true }).isVisible().catch(() => false)
  record('activation updates the row optimistically', optimisticActive)
  await page.getByText('Teacher reactivated.').waitFor({ timeout: 20000 })
  let users = (await api('/api/auth/users', ADMIN_TOKEN)).body.users || []
  record('activation is confirmed by the backend', userById(users, INACTIVE_ID)?.is_active === true)
  await page.unroute(`**/api/auth/users/${INACTIVE_ID}/toggle-active`)

  // Deactivation with delayed response.
  await page.route(`**/api/auth/users/${ACTIVE_ID}/toggle-active`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await route.continue()
  })
  await page.locator('tr', { hasText: 'ux-active@test.local' }).getByTitle('Deactivate').click()
  await page.getByRole('button', { name: 'Continue' }).click()
  const optimisticInactive = await page.locator('tr', { hasText: 'ux-active@test.local' })
    .getByText('inactive', { exact: true }).isVisible().catch(() => false)
  record('deactivation updates the row optimistically', optimisticInactive)
  await page.getByText('Teacher deactivated.').waitFor({ timeout: 20000 })
  users = (await api('/api/auth/users', ADMIN_TOKEN)).body.users || []
  record('deactivation is confirmed by the backend', userById(users, ACTIVE_ID)?.is_active === false)
  await page.unroute(`**/api/auth/users/${ACTIVE_ID}/toggle-active`)

  // Failure rollback + retry. Make the active teacher inactive again first.
  await page.locator('tr', { hasText: 'ux-active@test.local' }).getByTitle('Reactivate').click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByText('Teacher reactivated.').waitFor({ timeout: 20000 })

  let attempts = 0
  await page.route(`**/api/auth/users/${ACTIVE_ID}/toggle-active`, async (route) => {
    attempts += 1
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal database failure' }),
    })
  })
  await page.locator('tr', { hasText: 'ux-active@test.local' }).getByTitle('Deactivate').click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByText('Could not deactivate this teacher').waitFor({ timeout: 20000 })
  const rolledBack = await page.locator('tr', { hasText: 'ux-active@test.local' })
    .getByText('active', { exact: true }).isVisible().catch(() => false)
  users = (await api('/api/auth/users', ADMIN_TOKEN)).body.users || []
  record('failed deactivation rolls the row back', rolledBack)
  record('failed deactivation leaves the server unchanged', userById(users, ACTIVE_ID)?.is_active === true)
  record('failed deactivation shows friendly text', !(await page.getByText(/Internal database failure/).isVisible().catch(() => false)))

  await page.unroute(`**/api/auth/users/${ACTIVE_ID}/toggle-active`)
  await page.getByRole('button', { name: 'Try again' }).click()
  await page.getByText('Teacher deactivated.').waitFor({ timeout: 20000 })
  users = (await api('/api/auth/users', ADMIN_TOKEN)).body.users || []
  record('retry repeats the deactivation', userById(users, ACTIVE_ID)?.is_active === false, `attempts=${attempts}`)

  // Duplicate-submit prevention with a pending request.
  await page.locator('tr', { hasText: 'ux-active@test.local' }).getByTitle('Reactivate').click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByText('Teacher reactivated.').waitFor({ timeout: 20000 })

  let putCount = 0
  await page.route(`**/api/auth/users/${ACTIVE_ID}/toggle-active`, async (route) => {
    putCount += 1
    await new Promise((resolve) => setTimeout(resolve, 1500))
    await route.continue()
  })
  await page.locator('tr', { hasText: 'ux-active@test.local' }).getByTitle('Deactivate').click()
  await page.getByRole('button', { name: 'Continue' }).click()
  // The row action is disabled while actionId is pending.
  await page.waitForTimeout(300)
  const disabled = await page.locator('tr', { hasText: 'ux-active@test.local' }).getByTitle('Reactivate').isDisabled().catch(() => false)
  await page.waitForTimeout(1800)
  record('repeated clicks cannot duplicate the mutation', putCount === 1 && disabled, `puts=${putCount}`)
  await page.unroute(`**/api/auth/users/${ACTIVE_ID}/toggle-active`)

  // Authorization: a teacher cannot use the admin control or endpoint.
  const teacherContext = await browser.newContext()
  await teacherContext.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, {
    token: TEACHER_TOKEN,
    user: { id: 'teacher', email: 'teacher@test.local', full_name: 'Teacher', role: 'teacher', is_admin: false, is_active: true, school_id: null },
  })
  const teacherPage = await teacherContext.newPage()
  await teacherPage.goto(`${WEB}/school-admin/teachers`, { waitUntil: 'domcontentloaded' })
  await teacherPage.waitForTimeout(1200)
  await teacherPage.waitForURL(/\/login|\/dashboard/, { timeout: 10000 }).catch(() => {})
  const adminUi = await teacherPage.getByRole('button', { name: 'Add Teacher' }).isVisible().catch(() => false)
  record('teacher cannot open the admin teacher UI', !adminUi && !teacherPage.url().includes('/school-admin/teachers'), teacherPage.url())
  const forbidden = await api(`/api/auth/users/${ACTIVE_ID}/toggle-active`, TEACHER_TOKEN, { method: 'PUT' })
  record('teacher backend toggle is rejected', [401, 403].includes(forbidden.status), `status=${forbidden.status}`)

  await browser.close()
  const failed = results.filter((r) => !r.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
}).finally(() => setTimeout(() => process.exit(process.exitCode || 0), 500))
