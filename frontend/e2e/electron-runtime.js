/**
 * Isolated Electron runtime acceptance.
 *
 * Uses the real desktop main process with env-overridden ports and an isolated
 * user-data directory. Nothing touches the production app or another local app.
 */
const { _electron } = require('playwright')
const path = require('path')
const fs = require('fs')

const DESKTOP = path.resolve(__dirname, '..', '..', 'desktop')
const ELECTRON = path.join(DESKTOP, 'node_modules', 'electron', 'dist', 'electron.exe')
const USER_DATA = path.join(require('os').tmpdir(), 'opencode', 'schemeknit-electron-ux')
const BACKEND_PORT = 18334
const FRONTEND_URL = process.env.UX_WEB_URL || 'http://127.0.0.1:3100'
const results = []
function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

async function main() {
  fs.rmSync(USER_DATA, { recursive: true, force: true })
  fs.mkdirSync(USER_DATA, { recursive: true })

  const app = await _electron.launch({
    executablePath: ELECTRON,
    args: ['.'],
    cwd: DESKTOP,
    env: {
      ...process.env,
      SCHEMEKNIT_BACKEND_PORT: String(BACKEND_PORT),
      SCHEMEKNIT_FRONTEND_PORT: '18335',
      SCHEMEKNIT_DEV_FRONTEND_URL: FRONTEND_URL,
      SCHEMEKNIT_USER_DATA_DIR: USER_DATA,
      SCHEMEKNIT_PYTHON: process.env.SCHEMEKNIT_PYTHON || 'python',
    },
  })

  const page = await app.firstWindow({ timeout: 120000 })
  await page.waitForLoadState('domcontentloaded')
  const url = page.url()
  record('Electron loads the SchemeKnit UI, not another local app', url.startsWith(FRONTEND_URL), url)
  const title = await page.title()
  record('renderer is not blank', (await page.locator('body').innerText()).trim().length > 20, title)

  let health = 0
  for (let i = 0; i < 60; i += 1) {
    health = await page.evaluate(async (port) => {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/api/health`)
        return response.status
      } catch {
        return 0
      }
    }, BACKEND_PORT)
    if (health === 200) break
    await page.waitForTimeout(1000)
  }
  record('isolated desktop backend is reachable', health === 200, `status=${health}`)

  const base = await page.evaluate(() => window.electronAPI.backendUrl)
  record('renderer uses the configured backend port', base === `http://127.0.0.1:${BACKEND_PORT}`, base)

  // Safe first-run setup in the disposable desktop database.
  const email = `electron-ux-${Date.now()}@test.local`
  const password = 'ElectronUx!2026'
  const setup = await page.evaluate(async ({ base, email, password }) => {
    const status = await fetch(`${base}/api/auth/setup/status`).then((r) => r.json())
    if (status.needs_setup) {
      await fetch(`${base}/api/auth/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Electron UX Admin', email, password, school_name: 'Electron Test School',
        }),
      })
    }
    const login = await fetch(`${base}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, entry: 'school_admin' }),
    })
    return { status: login.status, body: await login.json().catch(() => null) }
  }, { base, email, password })
  record('desktop account setup and login work', setup.status === 200, `status=${setup.status}`)
  if (setup.status !== 200) throw new Error('desktop login failed')

  await page.evaluate(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: setup.body.access_token, user: setup.body.user })

  await page.route('**/api/documents/', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await route.continue()
  })
  await page.goto(`${FRONTEND_URL}/dashboard`, { waitUntil: 'domcontentloaded' })
  const skeleton = await page.getByText('Loading your dashboard')
    .waitFor({ state: 'attached', timeout: 5000 }).then(() => true).catch(() => false)
  record('dashboard skeleton renders in Electron', skeleton)
  await page.getByText(/Welcome back/i).waitFor({ timeout: 30000 })
  record('desktop dashboard loads real content', true)
  await page.unroute('**/api/documents/')

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByText(/Welcome back/i).waitFor({ timeout: 30000 })
  record('reload keeps the desktop session working', true)

  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))
  await page.goto(`${FRONTEND_URL}/settings`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1000)
  record('settings route loads in Electron', await page.getByText('Settings').first().isVisible())
  record('no renderer exceptions', errors.length === 0, errors.slice(0, 2).join(' | '))

  // Draft persistence across a real Electron close/reopen with the same
  // isolated user-data directory.
  await page.goto(`${FRONTEND_URL}/weekly-plans/new`, { waitUntil: 'domcontentloaded' })
  const week = page.getByLabel('Week number')
  await week.waitFor({ timeout: 30000 })
  await page.waitForTimeout(1000)
  await week.fill('9')
  await page.waitForTimeout(1600)
  const draftSaved = await page.evaluate(() => (
    Object.keys(localStorage).some((key) => key.includes('weekly-plan-new'))
  ))
  record('draft is written to Electron local storage', draftSaved)

  await app.close()
  record('Electron exits cleanly', true)

  const app2 = await _electron.launch({
    executablePath: ELECTRON,
    args: ['.'],
    cwd: DESKTOP,
    env: {
      ...process.env,
      SCHEMEKNIT_BACKEND_PORT: String(BACKEND_PORT),
      SCHEMEKNIT_FRONTEND_PORT: '18335',
      SCHEMEKNIT_DEV_FRONTEND_URL: FRONTEND_URL,
      SCHEMEKNIT_USER_DATA_DIR: USER_DATA,
      SCHEMEKNIT_PYTHON: process.env.SCHEMEKNIT_PYTHON || 'python',
    },
  })
  const page2 = await app2.firstWindow({ timeout: 120000 })
  await page2.waitForLoadState('domcontentloaded')
  let login2 = null
  for (let i = 0; i < 60 && !login2; i += 1) {
    login2 = await page2.evaluate(async ({ port, email, password }) => {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, entry: 'school_admin' }),
        })
        return response.ok ? await response.json() : null
      } catch {
        return null
      }
    }, { port: BACKEND_PORT, email, password })
    if (!login2) await page2.waitForTimeout(1000)
  }
  if (login2) {
    await page2.evaluate(({ token, user }) => {
      sessionStorage.setItem('teachflow_token', token)
      sessionStorage.setItem('teachflow_user', JSON.stringify(user))
    }, { token: login2.access_token, user: login2.user })
    await page2.goto(`${FRONTEND_URL}/weekly-plans/new`, { waitUntil: 'domcontentloaded' })
    const recovered = await page2.getByText(/We found your unsaved work/).first()
      .waitFor({ state: 'visible', timeout: 10000 }).then(() => true).catch(() => false)
    record('draft survives Electron close and reopen', recovered)
    if (recovered) {
      await page2.getByRole('button', { name: 'Continue draft' }).click()
      record('reopened draft restores its value',
        (await page2.getByLabel('Week number').inputValue()) === '9')
    }
  } else {
    record('draft survives Electron close and reopen', false, 'relaunch login failed')
  }
  await app2.close()
  record('second Electron session exits cleanly', true)
  const failed = results.filter((item) => !item.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  console.log('ports:', { backend: BACKEND_PORT, frontend: 18335, devFrontend: FRONTEND_URL })
  console.log('userData:', USER_DATA)
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.error('ELECTRON_FAIL', error)
  process.exitCode = 1
}).finally(() => setTimeout(() => process.exit(process.exitCode || 0), 500))
