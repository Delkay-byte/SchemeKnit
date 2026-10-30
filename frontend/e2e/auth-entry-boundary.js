// Authentication entry-point boundary â€” real browser journey.
//
// Proves that the teacher entry and the platform-admin entry authenticate only
// their own role, that a cross-entry login shows the generic error and stores
// no session, and that legitimate logins still reach their dashboards.
//
// Env: TF_WEB_URL (default http://localhost:3100),
//      TF_API_URL (default http://localhost:8000),
//      TF_BOOTSTRAP_SECRET (required: one-time platform-admin bootstrap secret).
const { chromium } = require('playwright')

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3100').replace(/\/$/, '')
const API = (process.env.TF_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const SECRET = process.env.TF_BOOTSTRAP_SECRET || ''
const STAMP = Date.now()
const TEACHER_EMAIL = `entry.teacher.${STAMP}@schemeknit.test`
const TEACHER_PASS = 'Entry#2026'
const ADMIN_EMAIL = `entry.admin.${STAMP}@schemeknit.test`
const ADMIN_PASS = 'Admin#2026'

let pass = 0
let fail = 0
function log(ok, label, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  â€” ${detail}` : ''}`)
  if (ok) pass += 1
  else fail += 1
}

async function role(page) {
  return page.evaluate(() => {
    const raw = sessionStorage.getItem('teachflow_user')
    return raw ? JSON.parse(raw).role : null
  })
}

async function signupTeacher(page) {
  await page.goto(`${WEB}/signup`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.locator('#signup-name').waitFor({ timeout: 30000 })
  await page.locator('#signup-name').fill('Entry Teacher')
  await page.locator('#signup-email').fill(TEACHER_EMAIL)
  await page.locator('#signup-password').fill(TEACHER_PASS)
  await page.locator('#signup-confirm').fill(TEACHER_PASS)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 60000 })
}

async function login(page, path, email, password) {
  await page.goto(`${WEB}${path}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.locator('input[type="email"]').waitFor({ timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
}

;(async () => {
  if (!SECRET) {
    console.error('Set TF_BOOTSTRAP_SECRET to run the platform-admin journey.')
    process.exit(2)
  }
  const boot = await fetch(`${API}/api/auth/setup-platform-admin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      bootstrap_secret: SECRET,
      full_name: 'Entry Admin',
      email: ADMIN_EMAIL,
      password: ADMIN_PASS,
    }),
  })
  if (boot.status !== 200) {
    console.error(`bootstrap failed: HTTP ${boot.status}`)
    process.exit(2)
  }

  const browser = await chromium.launch({ headless: true })
  try {
    // 1. Signup auto-login uses the teacher entry.
    const ctxA = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const pa = await ctxA.newPage()
    await signupTeacher(pa)
    log((await role(pa)) === 'teacher', 'signup auto-login creates a teacher session', await role(pa))
    await ctxA.close()

    // 2. Teacher entry succeeds for a teacher.
    const ctxB = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const pb = await ctxB.newPage()
    await login(pb, '/login', TEACHER_EMAIL, TEACHER_PASS)
    await pb.waitForURL(/\/dashboard/, { timeout: 60000 })
    log((await role(pb)) === 'teacher', 'teacher account signs in via the teacher entry', await role(pb))
    await ctxB.close()

    // 3. Platform-admin credentials on the teacher entry are rejected.
    const ctxC = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const pc = await ctxC.newPage()
    await login(pc, '/login', ADMIN_EMAIL, ADMIN_PASS)
    const alertC = pc.locator('p[role="alert"]')
    await alertC.waitFor({ timeout: 30000 })
    const textC = await alertC.innerText()
    log(textC.includes('Invalid email or password'),
      'platform admin is rejected on the teacher entry with the generic error', textC)
    log(/\/login\/?$/.test(new URL(pc.url()).pathname), 'rejected admin stays on the teacher login', pc.url())
    log((await role(pc)) === null, 'rejected admin receives no session')
    await ctxC.close()

    // 4. Teacher credentials on the platform-admin entry are rejected.
    const ctxD = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const pd = await ctxD.newPage()
    await login(pd, '/login/platform-admin', TEACHER_EMAIL, TEACHER_PASS)
    const alertD = pd.locator('p[role="alert"]')
    await alertD.waitFor({ timeout: 30000 })
    const textD = await alertD.innerText()
    log(textD.includes('Invalid email or password'),
      'teacher is rejected on the platform-admin entry with the generic error', textD)
    log(pd.url().includes('/login/platform-admin'), 'rejected teacher stays on the admin login', pd.url())
    log((await role(pd)) === null, 'rejected teacher receives no admin session')
    await ctxD.close()

    // 5. Platform-admin entry succeeds for the admin.
    const ctxE = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const pe = await ctxE.newPage()
    await login(pe, '/login/platform-admin', ADMIN_EMAIL, ADMIN_PASS)
    await pe.waitForFunction(
      () => window.location.pathname === '/platform-admin/',
      null,
      { timeout: 60000 },
    )
    log((await role(pe)) === 'platform_admin', 'platform admin signs in via the admin entry', await role(pe))
    await pe.reload({ waitUntil: 'domcontentloaded' })
    await pe.waitForLoadState('networkidle').catch(() => {})
    log(new URL(pe.url()).pathname === '/platform-admin/', 'admin dashboard survives reload', pe.url())
    await ctxE.close()
  } finally {
    await browser.close()
  }

  console.log(`\n${pass} passed, ${fail} failed`)
  process.exit(fail ? 1 : 0)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
