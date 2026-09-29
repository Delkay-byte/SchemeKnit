/**
 * Ad-hoc verification (never committed — underscore prefix).
 *
 * 1. Settings tab: "Enable Maintenance" actually flips Maintenance Mode to ON,
 *    "Disable Maintenance" flips back to OFF (regression for the 500 NameError).
 * 2. Accounts tab: smart search box filters accounts by name/email/role,
 *    shows X-of-Y counter, no-match empty state, and restores on clear.
 *
 * Usage: node e2e/_pa-maintenance-accounts-check.js [baseUrl]
 * Requires: backend on :8000 + `npm run build` + `next start -p 3003`.
 */
const { chromium } = require('playwright')

const BASE = process.argv[2] || 'http://localhost:3003'
const PLATFORM = { email: 'accept.pa@schemeknit.test', password: 'Accept#2026' }

let pass = 0
let fail = 0
function log(ok, label, detail) {
  if (ok) pass++
  else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function login(page, entry, creds) {
  await page.goto(BASE + entry, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="email"]').fill(creds.email)
  await page.locator('input[type="password"]').fill(creds.password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
}

async function waitForSafe(locator, timeout = 15000) {
  try {
    await locator.first().waitFor({ state: 'visible', timeout })
    return true
  } catch (e) {
    return false
  }
}

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  try {
    await login(page, '/login/platform-admin', PLATFORM)
    log(!page.url().includes('/login'), 'login as platform admin succeeds', page.url())

    await page.goto(BASE + '/platform-admin/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})

    // ---- Maintenance toggle ----
    const settingsTab = page.locator('main [role="tab"]:has-text("settings")').first()
    log((await settingsTab.count()) > 0, 'settings tab present', '')
    await settingsTab.click()
    await page.waitForTimeout(600)
    log((await page.locator('[data-maintenance]').count()) >= 1,
      'settings: maintenance control present', '')
    log((await page.getByText(/Maintenance Mode: OFF/).count()) >= 1,
      'maintenance: initially OFF', '')

    await page.getByRole('button', { name: 'Enable Maintenance' }).click()
    const wentOn = await waitForSafe(page.getByText(/Maintenance Mode: ON/))
    log(wentOn, 'maintenance: Enable click flips to ON',
      wentOn ? '' : 'text "Maintenance Mode: ON" never appeared')
    log((await page.getByRole('button', { name: 'Disable Maintenance' }).count()) >= 1,
      'maintenance: button becomes Disable Maintenance', '')

    await page.getByRole('button', { name: 'Disable Maintenance' }).click()
    const wentOff = await waitForSafe(page.getByText(/Maintenance Mode: OFF/))
    log(wentOff, 'maintenance: Disable click flips back to OFF',
      wentOff ? '' : 'text "Maintenance Mode: OFF" never appeared')

    // ---- Accounts search ----
    const accountsTab = page.locator('main [role="tab"]:has-text("accounts")').first()
    log((await accountsTab.count()) > 0, 'accounts tab present', '')
    await accountsTab.click()
    await page.waitForTimeout(700)
    const rowsAll = await page.locator('main tbody tr').count()
    log(rowsAll >= 3, 'accounts: table lists accounts', `rows=${rowsAll}`)

    const search = page.locator('[data-account-search]')
    log((await search.count()) >= 1, 'accounts: smart search box present', '')

    await search.fill('accept')
    await page.waitForTimeout(250)
    const rowsAccept = await page.locator('main tbody tr').count()
    log(rowsAccept >= 1 && rowsAccept <= rowsAll,
      'accounts: search "accept" filters rows', `${rowsAccept}/${rowsAll}`)
    log((await page.getByText(/of \d+ shown/).count()) >= 1,
      'accounts: shows "X of Y shown" counter', '')

    await search.fill('pa@schemeknit')
    await page.waitForTimeout(250)
    const rowsPa = await page.locator('main tbody tr').count()
    log(rowsPa === 1, 'accounts: email fragment narrows to one account', `rows=${rowsPa}`)

    await search.fill('zzzz-no-match')
    await page.waitForTimeout(250)
    log((await page.getByText(/No accounts match/).count()) >= 1,
      'accounts: no-match empty state renders', '')
    log((await page.locator('main tbody tr').count()) === 0,
      'accounts: no rows while no match', `rows=${await page.locator('main tbody tr').count()}`)

    await search.fill('')
    await page.waitForTimeout(250)
    const rowsBack = await page.locator('main tbody tr').count()
    log(rowsBack === rowsAll, 'accounts: clearing search restores all rows',
      `${rowsBack}/${rowsAll}`)

    log(pageErrors.length === 0, 'zero page errors',
      pageErrors.slice(0, 3).join(' | ') || 'none')
  } catch (e) {
    log(false, 'script completed without thrown error', e.message)
  }
  console.log(`\n${pass} passed, ${fail} failed`)
  await browser.close()
  process.exit(fail === 0 ? 0 : 1)
})()
