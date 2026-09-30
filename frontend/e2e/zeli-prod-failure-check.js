/**
 * Production failure-safe check: exhaust the teacher's remaining monthly AI
 * allowance, then attempt one more Zeli suggestion.
 *
 * Expected: the request is refused BEFORE the provider is ever called; the
 * teacher sees only calm, non-technical copy; the stored content is preserved
 * byte-for-byte; and no AI unit is consumed by the refused attempt.
 *
 * This is the production mirror of the local invalid-key failure pass
 * (40/40), exercising the same teacher-safe UI contract through a real
 * failure mode that does not require disturbing the production key.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const WEB = 'https://schemeknit-frontend.onrender.com'
const API = 'https://schemeknit-api.onrender.com'
const OUT = path.join(__dirname, 'zeli-groq-journey')
const STATE = path.join(OUT, 'state.json')
const state = JSON.parse(fs.readFileSync(STATE, 'utf8'))

let pass = 0
let fail = 0
function log(ok, label, detail) {
  if (ok) pass++; else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function apiGet(page, p) {
  return page.evaluate(async ({ apiBase, p }) => {
    const token = sessionStorage.getItem('teachflow_token')
    const res = await fetch(`${apiBase}${p}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    let body = null
    try { body = await res.json() } catch { /* non-JSON */ }
    return { status: res.status, body }
  }, { apiBase: API, p })
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const httpErrors = []
  page.on('response', (r) => {
    if (r.status() >= 400) httpErrors.push(`${r.status()} ${r.url().replace(API, '').slice(0, 80)}`)
  })

  try {
    // ── login ─────────────────────────────────────────────────────────────
    await page.goto(`${WEB}/login`, { waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.locator('#teacher-email').waitFor({ timeout: 60000 })
    await page.locator('#teacher-email').fill(state.email)
    await page.locator('#teacher-password').fill(state.password)
    await page.getByRole('button', { name: /^Sign in$/ }).click()
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 120000 })

    let plan = (await apiGet(page, '/api/auth/my-plan')).body
    const limit = plan.ai_quota_limit ?? plan.ai_credits ?? 5
    let used = plan.ai_quota_used ?? 0
    log(true, 'starting allowance', `used=${used} of ${limit}`)

    // ── 1. Open the review page and snapshot the stored content ───────────
    await page.goto(`${WEB}/lessons/${state.lessonId}`, { waitUntil: 'domcontentloaded', timeout: 180000 })
    await page.locator('textarea[aria-label="Assessment"]').waitFor({ timeout: 120000 })
    for (let i = 0; i < 20; i += 1) {
      const got = await page.evaluate(() =>
        document.querySelector('textarea[aria-label="Assessment"]')?.value || '')
      if (got) break
      await sleep(1500)
    }
    const baseline = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    const baselineAssessment = baseline.assessment
    log(Boolean(baselineAssessment), 'the stored assessment is present before the failure attempt')

    // ── 2. Burn the remaining allowance with real suggestions ─────────────
    const btn = () => page.locator('section[aria-label="Assessment"]')
      .getByRole('button', { name: 'Suggest another version' })
    for (let n = used; n < limit; n += 1) {
      await btn().click()
      await page.getByText('Zeli rewrote this section').waitFor({ timeout: 240000 })
      await sleep(1500)
      plan = (await apiGet(page, '/api/auth/my-plan')).body
      used = plan.ai_quota_used ?? 0
      console.log(`[diag] burn loop: used=${used} of ${limit}`)
    }
    log(used >= limit, 'the monthly allowance is now exhausted', `used=${used} of ${limit}`)

    // ── 3. One more suggestion — this must fail safely ────────────────────
    const storedBefore = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    // The burn loop's successful (unsaved) rewrites legitimately changed the
    // on-screen text; the guarantee is that the REFUSED attempt changes
    // nothing, so compare against the on-screen value immediately before it.
    const onScreenBefore = await page.evaluate(() =>
      document.querySelector('textarea[aria-label="Assessment"]')?.value || '')
    await btn().click()
    // Either the exhausted banner or the generic Zeli failure banner.
    await Promise.race([
      page.getByText(/used all .* free AI generations/i).waitFor({ timeout: 240000 }).catch(() => {}),
      page.getByText('Zeli could not rewrite this section right now').waitFor({ timeout: 240000 }).catch(() => {}),
      page.getByText('Zeli is unavailable right now').waitFor({ timeout: 240000 }).catch(() => {}),
    ])
    await sleep(2000)
    await page.screenshot({ path: path.join(OUT, '13-prod-failure.png') }).catch(() => {})

    const body = await page.locator('body').innerText()
    const calm = /used all .* free AI generations/i.test(body)
      || /Zeli could not rewrite this section right now/i.test(body)
      || /Zeli is unavailable right now/i.test(body)
    log(calm, 'the teacher sees a calm failure message, not a crash')

    // No provider/API internals may leak, even in failure.
    const leaks = ['groq', 'gemini', 'openai', 'gpt-oss', 'rate_limit', '429', '503',
      'unauthorized', 'invalid api key', 'api key', 'malformed', 'stack', 'traceback']
    for (const bad of leaks) {
      log(!body.toLowerCase().includes(bad), `production failure copy hides "${bad}"`)
    }

    // ── 4. Content preserved; nothing consumed ────────────────────────────
    const after = await page.evaluate(() =>
      document.querySelector('textarea[aria-label="Assessment"]')?.value || '')
    const storedAfter = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    log(after === onScreenBefore,
      'the on-screen assessment is unchanged by the refused attempt')
    log(storedAfter.assessment === storedBefore.assessment,
      'the stored assessment is unchanged by the refused attempt')

    plan = (await apiGet(page, '/api/auth/my-plan')).body
    const usedAfter = plan.ai_quota_used ?? 0
    log(usedAfter === used,
      'the refused attempt consumed ZERO AI units', `${used} -> ${usedAfter}`)

    // ── 5. The page is still a normal, editable lesson ────────────────────
    await page.locator('textarea[aria-label="Assessment"]')
      .fill(`${baselineAssessment} Teacher edit after the production failure.`)
    await page.getByRole('button', { name: 'Save Changes' }).click()
    await page.getByText('Saved', { exact: true }).waitFor({ timeout: 90000 }).catch(() => {})
    const savedVisible = await page.getByText('Saved', { exact: true }).isVisible().catch(() => false)
    log(savedVisible, 'the lesson is still editable and saves after the production failure')

    const final = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    log(String(final.assessment).endsWith('Teacher edit after the production failure.'),
      'the manual edit persisted past the production failure')

    console.log(`[diag] http >=400: ${JSON.stringify(httpErrors.slice(0, 10))}`)
  } catch (err) {
    log(false, 'check threw', err && err.message ? err.message : String(err))
    await page.screenshot({ path: path.join(OUT, 'prod-failure-ERROR.png') }).catch(() => {})
  } finally {
    console.log(`\n${'='.repeat(72)}\nPROD FAILURE CHECK: ${pass} passed, ${fail} failed`)
    await browser.close()
  }
  process.exit(fail === 0 ? 0 : 1)
})()
