/**
 * TAB-ISOLATED AUTH acceptance.
 *
 * Proves that authentication is isolated per browser tab while sharing
 * ONE browser, ONE browser context, ONE origin:
 *   - Tab A = teacher, Tab B = school admin, Tab C = platform admin
 *     simultaneously, with server-verified identities (API /auth/me).
 *   - Logout in one tab never logs out another.
 *   - Reload never changes a tab's identity.
 *   - A genuinely new tab (or a pasted protected URL) starts
 *     unauthenticated — it never inherits an existing tab's identity.
 *   - Actual API request credentials are captured and compared
 *     (distinct Bearer tokens, no auth cookies).
 *
 * Usage: node e2e/tab-isolated-auth-acceptance.js [baseUrl]
 * Requires: npm run build + next start already running (and the backend).
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = (process.argv[2] || 'http://localhost:3003').replace(/\/$/, '')
const API = process.env.API_BASE || 'http://localhost:8000'
const OUT = path.join(__dirname, 'tab-isolated-auth-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const PASSWORD = process.env.ACCEPT_PASSWORD || 'Accept#2026'
const ACCOUNTS = {
  teacher: { email: process.env.TEACHER_EMAIL || 'accept.teacher@schemeknit.test', id: 'accept-teacher-0001', role: 'teacher', home: /\/dashboard/ },
  schoolAdmin: { email: process.env.SA_EMAIL || 'accept.sa@schemeknit.test', id: 'accept-sa-0001', role: 'school_admin', home: /\/school-admin/ },
  platformAdmin: { email: process.env.PA_EMAIL || 'accept.pa@schemeknit.test', id: 'accept-pa-0001', role: 'platform_admin', home: /\/platform-admin/ },
}

let pass = 0
let fail = 0
const results = []
const captured = []

function log(ok, label, detail) {
  if (ok) pass++
  else fail++
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function shot(page, name) {
  try { await page.screenshot({ path: path.join(OUT, name), fullPage: false }) } catch { /* page may be closed */ }
}

/** Capture every API request this page makes: bearer token + cookie evidence. */
function track(page, tabName, pageErrors) {
  page.on('request', (req) => {
    const url = req.url()
    if (!url.startsWith(API)) return
    const h = req.headers()
    captured.push({
      tab: tabName,
      url: url.replace(API, ''),
      auth: h.authorization || '',
      cookie: h.cookie || '',
    })
  })
  page.on('pageerror', (err) => pageErrors.push(`${tabName}: ${err.message}`))
}

async function authState(page) {
  return page.evaluate(() => {
    const t = sessionStorage.getItem('teachflow_token')
    const u = sessionStorage.getItem('teachflow_user')
    return {
      token: t,
      user: u ? JSON.parse(u) : null,
      legacyLsToken: localStorage.getItem('teachflow_token'),
      legacyLsUser: localStorage.getItem('teachflow_user'),
      path: location.pathname,
    }
  })
}

/** Server-verified identity FROM WITHIN the tab (uses that tab's own token). */
async function pageMe(page) {
  return page.evaluate(async (api) => {
    const token = sessionStorage.getItem('teachflow_token')
    if (!token) return { status: 0, id: null, email: null }
    try {
      const res = await fetch(api + '/api/auth/me', {
        headers: { Authorization: 'Bearer ' + token },
      })
      const data = await res.json().catch(() => null)
      return { status: res.status, id: data && data.id, email: data && data.email, role: data && data.role }
    } catch (e) {
      return { status: -1, id: null, error: String(e) }
    }
  }, API)
}

async function login(page, acct) {
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})
  await page.locator('input[type="email"]').first().fill(acct.email)
  await page.locator('input[type="password"]').first().fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(acct.home, { timeout: 25000 })
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const pageErrors = []

  // ── TAB A: teacher login ─────────────────────────────────────────
  const pageA = await context.newPage()
  track(pageA, 'A', pageErrors)
  await login(pageA, ACCOUNTS.teacher)
  await pageA.waitForTimeout(1200)

  const a1 = await authState(pageA)
  log(!!a1.token && a1.user && a1.user.id === ACCOUNTS.teacher.id, 'A: teacher logged in', `${a1.user && a1.user.email} path=${a1.path}`)
  log(a1.legacyLsToken === null && a1.legacyLsUser === null, 'A: no legacy localStorage auth keys', `ls=${a1.legacyLsToken}`)
  await shot(pageA, 'a-teacher-dashboard.png')

  // ── TAB B: fresh same-origin page must start UNAUTHENTICATED ─────
  const pageB = await context.newPage()
  track(pageB, 'B', pageErrors)
  await pageB.goto(BASE + '/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await pageB.waitForURL(/\/login/, { timeout: 20000 }).catch(() => {})
  await pageB.waitForTimeout(800)
  const bFresh = await authState(pageB)
  log(!bFresh.token && !bFresh.user, 'B: fresh tab on protected URL is unauthenticated', `path=${bFresh.path}`)
  log(bFresh.legacyLsToken === null, 'B: no legacy localStorage auth keys', `ls=${bFresh.legacyLsToken}`)

  // ── TAB B: school admin login ────────────────────────────────────
  await login(pageB, ACCOUNTS.schoolAdmin)
  await pageB.waitForTimeout(1200)

  const a2 = await authState(pageA)
  const b2 = await authState(pageB)
  log(a2.user && a2.user.id === ACCOUNTS.teacher.id, 'A: still teacher after B logs in', `${a2.user && a2.user.id}`)
  log(b2.user && b2.user.id === ACCOUNTS.schoolAdmin.id, 'B: school admin logged in', `${b2.user && b2.user.id} path=${b2.path}`)
  log(a2.token && b2.token && a2.token !== b2.token, 'A and B hold DISTINCT bearer tokens', `len=${a2.token ? a2.token.length : 0}/${b2.token ? b2.token.length : 0}`)
  await shot(pageB, 'b-school-admin.png')

  // ── Server-verified identity from inside each tab ────────────────
  const meA = await pageMe(pageA)
  const meB = await pageMe(pageB)
  log(meA.status === 200 && meA.id === ACCOUNTS.teacher.id, 'A: /api/auth/me resolves teacher', `status=${meA.status} id=${meA.id}`)
  log(meB.status === 200 && meB.id === ACCOUNTS.schoolAdmin.id, 'B: /api/auth/me resolves school admin', `status=${meB.status} id=${meB.id}`)

  // ── Reload must not change identity ──────────────────────────────
  await pageA.reload({ waitUntil: 'domcontentloaded' })
  await pageA.waitForTimeout(1000)
  await pageB.reload({ waitUntil: 'domcontentloaded' })
  await pageB.waitForTimeout(1000)
  const meA2 = await pageMe(pageA)
  const meB2 = await pageMe(pageB)
  log(meA2.status === 200 && meA2.id === ACCOUNTS.teacher.id, 'A: reload keeps teacher identity', `id=${meA2.id}`)
  log(meB2.status === 200 && meB2.id === ACCOUNTS.schoolAdmin.id, 'B: reload keeps school-admin identity', `id=${meB2.id}`)

  // ── LOGOUT ISOLATION: A logs out, B must be untouched ────────────
  await pageA.locator('button[aria-label="Log out"]:visible').first().click()
  await pageA.waitForURL(/\/login/, { timeout: 15000 }).catch(() => {})
  await pageA.waitForTimeout(500)
  const aOut = await authState(pageA)
  log(!aOut.token && !aOut.user, 'A: logout clears THIS tab only', `path=${aOut.path}`)

  // Immediately exercise an authenticated API call from B.
  const meBAfterAOut = await pageMe(pageB)
  const bAlive = await authState(pageB)
  log(meBAfterAOut.status === 200 && meBAfterAOut.id === ACCOUNTS.schoolAdmin.id,
    'B: still authenticated right after A logs out',
    `status=${meBAfterAOut.status} id=${meBAfterAOut.id}`)
  log(!!bAlive.token, 'B: token intact after A logout', `path=${bAlive.path}`)
  await shot(pageA, 'a-after-logout.png')
  await shot(pageB, 'b-during-a-logout.png')

  // ── A logs back in: both tabs coexist again ──────────────────────
  await login(pageA, ACCOUNTS.teacher)
  await pageA.waitForTimeout(800)
  const meA3 = await pageMe(pageA)
  const meB3 = await pageMe(pageB)
  log(meA3.status === 200 && meA3.id === ACCOUNTS.teacher.id, 'A: re-login restores teacher', `id=${meA3.id}`)
  log(meB3.status === 200 && meB3.id === ACCOUNTS.schoolAdmin.id, 'B: unaffected by A re-login', `id=${meB3.id}`)

  // ── TAB C: new tab inherits nothing (A is authenticated) ─────────
  const pageC = await context.newPage()
  track(pageC, 'C', pageErrors)
  await pageC.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await pageC.waitForTimeout(800)
  const cLanding = await authState(pageC)
  log(!cLanding.token && !cLanding.user, 'C: new tab on landing starts unauthenticated', `path=${cLanding.path}`)

  await pageC.goto(BASE + '/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await pageC.waitForURL(/\/login/, { timeout: 20000 }).catch(() => {})
  await pageC.waitForTimeout(600)
  const cProtected = await authState(pageC)
  log(!cProtected.token && /^\/login\/?$/.test(cProtected.path), 'C: pasted protected URL stays unauthenticated (no inheritance)', `path=${cProtected.path}`)

  // ── TAB C: platform admin login → three identities coexist ───────
  await login(pageC, ACCOUNTS.platformAdmin)
  await pageC.waitForTimeout(1200)
  const meC = await pageMe(pageC)
  const meA4 = await pageMe(pageA)
  const meB4 = await pageMe(pageB)
  log(meC.status === 200 && meC.id === ACCOUNTS.platformAdmin.id, 'C: /api/auth/me resolves platform admin', `status=${meC.status} id=${meC.id} path=${(await authState(pageC)).path}`)
  log(meA4.status === 200 && meA4.id === ACCOUNTS.teacher.id, 'A: still teacher with 3 tabs open', `id=${meA4.id}`)
  log(meB4.status === 200 && meB4.id === ACCOUNTS.schoolAdmin.id, 'B: still school admin with 3 tabs open', `id=${meB4.id}`)
  await shot(pageC, 'c-platform-admin.png')

  // ── API DATA ISOLATION: cross-check via Node using each tab token ─
  const nodeMe = async (token) => {
    try {
      const res = await fetch(`${API}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      const data = await res.json().catch(() => null)
      return { status: res.status, id: data && data.id, email: data && data.email, role: data && data.role }
    } catch (e) { return { status: -1, error: String(e) } }
  }
  const cState = await authState(pageC)
  const nA = await nodeMe(a2.token)
  const nB = await nodeMe(b2.token)
  const nC = await nodeMe(cState.token)
  log(nA.status === 200 && nA.id === ACCOUNTS.teacher.id, 'API: A token resolves teacher', `${nA.status} ${nA.email}`)
  log(nB.status === 200 && nB.id === ACCOUNTS.schoolAdmin.id, 'API: B token resolves school admin', `${nB.status} ${nB.email}`)
  log(nC.status === 200 && nC.id === ACCOUNTS.platformAdmin.id, 'API: C token resolves platform admin', `${nC.status} ${nC.email}`)

  // ── ROLE ISOLATION (server-side, nothing loosened) ───────────────
  const nodeStatus = async (token, apiPath) => {
    try {
      const res = await fetch(`${API}${apiPath}`, { headers: { Authorization: `Bearer ${token}` } })
      return res.status
    } catch (e) { return -1 }
  }
  const teacherToPlatform = await nodeStatus(a2.token, '/api/platform-admin/dashboard')
  const saToPlatform = await nodeStatus(b2.token, '/api/platform-admin/dashboard')
  const paToPlatform = await nodeStatus(cState.token, '/api/platform-admin/dashboard')
  log(teacherToPlatform === 403, 'role: teacher forbidden from platform-admin API', `status=${teacherToPlatform}`)
  log(saToPlatform === 403, 'role: school admin forbidden from platform-admin API', `status=${saToPlatform}`)
  log(paToPlatform === 200, 'role: platform admin allowed on platform-admin API', `status=${paToPlatform}`)
  const teacherToUsers = await nodeStatus(a2.token, '/api/auth/users')
  const saToUsers = await nodeStatus(b2.token, '/api/auth/users')
  log(teacherToUsers === 403, 'role: teacher forbidden from user list', `status=${teacherToUsers}`)
  log(saToUsers === 200, 'role: school admin allowed on user list', `status=${saToUsers}`)

  // ── SESSION EXPIRATION / INVALIDATION ISOLATION ──────────────────
  // Corrupt ONLY Tab A's stored token: A's next API call must 401 and
  // A alone gets logged out; B and C must be untouched.
  await pageA.evaluate(() => {
    const t = sessionStorage.getItem('teachflow_token')
    if (t) sessionStorage.setItem('teachflow_token', t + 'corrupted')
  })
  await pageA.reload({ waitUntil: 'domcontentloaded' })
  await pageA.waitForTimeout(1500)
  const aInvalid = await authState(pageA)
  const meB5 = await pageMe(pageB)
  const meC5 = await pageMe(pageC)
  log(!aInvalid.token && aInvalid.path.startsWith('/login'), 'invalid A session: A alone logged out', `path=${aInvalid.path} token=${!!aInvalid.token}`)
  log(meB5.status === 200 && meB5.id === ACCOUNTS.schoolAdmin.id, 'invalid A session: B unaffected', `status=${meB5.status}`)
  log(meC5.status === 200 && meC5.id === ACCOUNTS.platformAdmin.id, 'invalid A session: C unaffected', `status=${meC5.status}`)

  // Restore A for the credential-capture assertions (fresh login).
  await login(pageA, ACCOUNTS.teacher)
  await pageA.waitForTimeout(800)

  // ── REQUEST-LEVEL EVIDENCE (captured across the whole run) ───────
  const apiReqs = captured.filter((c) => c.url.startsWith('/api/'))
  const withAuth = apiReqs.filter((c) => c.auth.startsWith('Bearer '))
  const withCookie = apiReqs.filter((c) => c.cookie && c.cookie.trim().length > 0)
  log(apiReqs.length > 0, 'captured API requests from all tabs', `total=${apiReqs.length}`)
  log(withAuth.length > 0, 'authenticated API requests carry Authorization: Bearer', `bearer=${withAuth.length}/${apiReqs.length}`)
  log(withCookie.length === 0, 'NO request carries a Cookie header (no shared session cookie)', `cookie-reqs=${withCookie.length}`)

  const bearerByTab = {}
  for (const c of withAuth) {
    if (!bearerByTab[c.tab]) bearerByTab[c.tab] = new Set()
    bearerByTab[c.tab].add(c.auth)
  }
  const distinctAcrossTabs = () => {
    const tabs = Object.keys(bearerByTab)
    if (tabs.length < 2) return false
    const union = new Set()
    for (const t of tabs) for (const v of bearerByTab[t]) union.add(v)
    return union.size >= tabs.length
  }
  log(distinctAcrossTabs(), 'each tab authenticated with its OWN bearer token',
    JSON.stringify(Object.fromEntries(Object.entries(bearerByTab).map(([k, v]) => [k, v.size]))))

  // ── Global storage audit ─────────────────────────────────────────
  for (const [name, pg] of [['A', pageA], ['B', pageB], ['C', pageC]]) {
    const s = await authState(pg)
    log(s.legacyLsToken === null && s.legacyLsUser === null, `${name}: final legacy localStorage check clean`, `ls=${s.legacyLsToken}`)
    log(!!s.token, `${name}: still authenticated in its own tab`, `path=${s.path}`)
  }

  log(pageErrors.length === 0, 'no uncaught page errors in any tab', pageErrors.slice(0, 3).join(' | '))

  await browser.close()

  const summary = `Tab-isolated auth acceptance — ${new Date().toISOString()}\nBASE=${BASE} API=${API}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(`Tab-isolated auth acceptance: ${pass} pass, ${fail} fail`)
  if (fail > 0) {
    console.log(results.filter((r) => r.startsWith('FAIL')).join('\n'))
    process.exit(1)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
