/**
 * SchemeKnit "Generate with Zeli" whole-lesson journey (real app, real backend).
 *
 * Proves the NEW generation method is a real, selectable option alongside the
 * existing Standard (OFF/BASIC/ENHANCED) path:
 *
 *   sign up -> upload a real Computing scheme -> generate page
 *     -> "Generate with Zeli" is visible and selected -> backend reports ready
 *     -> the enrichment AI Mode select is disabled with a stated reason
 *     -> generate -> lessons exist with generation_method=zeli + prompt provider
 *     -> the result says Zeli generated the lessons (no fake deterministic copy)
 *     -> back on the setup surface, Standard re-enables OFF/BASIC/ENHANCED
 *
 * Requires: backend on TF_API_URL and frontend on TF_WEB_URL.
 * Uses a working provider only when the backend is configured for it.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3002').replace(/\/$/, '')
const API = (process.env.TF_API_URL || 'http://127.0.0.1:8010').replace(/\/$/, '')
const ROOT = path.join(__dirname, '..', '..')
const SCHEME = process.env.TF_SCHEME_FILE
  ? path.resolve(process.env.TF_SCHEME_FILE)
  : path.join(ROOT, 'backend', 'tests', 'fixtures', 'remediation',
    'bs7_code_only_indicators_scheme.docx')
const OUT = path.join(__dirname, 'zeli-method-journey')
fs.mkdirSync(OUT, { recursive: true })

const STAMP = Date.now()
const EMAIL = `zeli.method.${STAMP}@schemeknit.test`
const PASSWORD = 'Zeli#2026'
const SCHOOL = 'Achimota Basic School'

let pass = 0
let fail = 0
const results = []

function log(ok, label, detail) {
  if (ok) pass++
  else fail++
  const line = `${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`
  results.push(line)
  console.log(line)
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitHydrated(page, probe, timeout = 30000) {
  const start = Date.now()
  const probeValue = `hydration-probe-${Date.now().toString(36)}`
  while (Date.now() - start < timeout) {
    const filled = await page.evaluate(({ sel, value }) => {
      const el = document.querySelector(sel)
      if (!el) return false
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value')?.set
      setter?.call(el, value)
      el.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    }, { sel: probe, value: probeValue }).catch(() => false)
    if (filled) {
      await sleep(1200)
      const kept = await page.evaluate(({ sel, value }) =>
        document.querySelector(sel)?.value === value, { sel: probe, value: probeValue }).catch(() => false)
      if (kept) return
    }
    await sleep(300)
  }
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false }).catch(() => {})
}

async function apiGet(page, p) {
  return page.evaluate(async ({ apiBase, p }) => {
    const token = sessionStorage.getItem('teachflow_token')
    const res = await fetch(`${apiBase}${p}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    let body = null
    try { body = await res.json() } catch { /* non-JSON */ }
    return { status: res.status, body }
  }, { apiBase: API, p })
}

async function signup(page) {
  await page.goto(`${WEB}/signup`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitHydrated(page, '#signup-name')
  await page.locator('#signup-name').fill('Zeli Method Teacher')
  await page.locator('#signup-email').fill(EMAIL)
  await page.locator('#signup-password').fill(PASSWORD)
  await page.locator('#signup-confirm').fill(PASSWORD)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 60000 })
}

async function setSchool(page) {
  await page.goto(`${WEB}/settings`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  const input = page.locator('#profile-school')
  await input.waitFor({ timeout: 30000 })
  await waitHydrated(page, '#profile-school')
  await input.fill(SCHOOL)
  await page.getByRole('button', { name: /save profile/i }).click()
  await page.waitForTimeout(1200)
}

async function uploadScheme(page) {
  await page.goto(`${WEB}/upload`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitHydrated(page, 'input[type="file"]')
  await page.locator('input[type="file"]').setInputFiles(SCHEME)
  await page.getByRole('button', { name: /upload & process/i }).click()
  const success = page.locator('[data-upload-success]')
  const picker = page.locator('[data-multi-subject]')
  await Promise.race([
    success.waitFor({ timeout: 120000 }).catch(() => {}),
    picker.waitFor({ timeout: 120000 }).catch(() => {}),
  ])
  const needsConfirm = !(await success.isVisible().catch(() => false))
  if (needsConfirm) {
    const classSelect = page.locator('#confirm-class-level')
    if (await classSelect.count()) {
      let options = []
      for (let i = 0; i < 30; i += 1) {
        options = await classSelect.locator('option').allInnerTexts()
        if (options.some((o) => /^Basic 7$/.test(o.trim()))) break
        await page.waitForTimeout(500)
      }
      const match = options.find((o) => o.trim() === 'Basic 7')
      if (match) await classSelect.selectOption({ label: match })
    }
    const buttons = page.locator('[data-multi-subject] button')
    if (await buttons.count()) await buttons.first().click()
    else {
      const fallback = page.locator('#confirm-fallback-subject')
      if (await fallback.count()) await fallback.selectOption({ label: 'Computing' })
      await page.getByRole('button', { name: /confirm/i }).first().click()
    }
  } else {
    await page.getByRole('button', { name: /review curriculum/i }).click()
  }
  await page.waitForURL(/\/(review|generate)\//, { timeout: 90000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  const url = page.url()
  const schemeId = (url.split(/\/review\//)[1] || url.split(/\/generate\//)[1] || '')
    .split(/[/?#]/)[0]
  return { schemeId, onGenerate: url.includes('/generate/') }
}

async function configure(page, onGenerate) {
  if (!onGenerate) {
    await page.getByRole('button', { name: /approve & configure/i }).last().click()
    await page.waitForURL(/\/generate\//, { timeout: 60000 })
  }
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('#cfg-ai-mode').waitFor({ timeout: 30000 })
  await page.locator('#cfg-term-start').fill('2026-09-14')
  await page.locator('#cfg-term-end').fill('2026-09-25')
  await page.locator('#cfg-lessons-per-week').fill('1')
  await page.locator('[data-lesson-review]').waitFor({ timeout: 120000 })
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  // The upload page records a one-shot Autopilot intent. This journey exercises
  // the manual method selector, so clear the intent before React mounts on the
  // destination page (addInitScript runs on every navigation).
  await ctx.addInitScript(() => {
    // Block only the one-shot Autopilot intent: client-side navigation does not
    // create a new document, so overriding the setter is what actually stops
    // the destination page from auto-generating before the teacher chooses.
    const original = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key === 'schemeknit.autopilot_intent') return
      return original.call(this, key, value)
    }
  })
  const page = await ctx.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(e.message))

  try {
    if (!fs.existsSync(SCHEME)) throw new Error(`scheme fixture missing: ${SCHEME}`)

    // ── 1. Account + real scheme ────────────────────────────────────────────
    await signup(page)
    log(true, 'fresh teacher account created', EMAIL)
    await setSchool(page)
    const schemeId = await uploadScheme(page)
    log(Boolean(schemeId.schemeId), 'real Computing scheme uploaded and extracted', schemeId.schemeId)

    // ── 2. Selection surface ────────────────────────────────────────────────
    await configure(page, schemeId.onGenerate)
    const zeliButton = page.locator('[data-generation-method="zeli"]')
    await zeliButton.waitFor({ timeout: 30000 })
    log(await zeliButton.isVisible(), '"Generate with Zeli" is offered')
    log((await page.locator('[data-generation-method="standard"]').count()) === 1,
      'Standard generation is still offered alongside it')

    await zeliButton.click()
    await page.waitForTimeout(2000)
    const zeliCount = await page.locator('[data-generation-method="zeli"]').count()
    console.log(`[diag] after zeli click url=${page.url()} zeliButtons=${zeliCount}`)
    if (!zeliCount) {
      console.log(`[diag] body=${(await page.locator('body').innerText()).slice(0, 400)}`)
    }
    log((await zeliButton.getAttribute('aria-pressed')) === 'true',
      'the Zeli method is the selected choice')
    log(await page.locator('#cfg-ai-mode').isDisabled(),
      'AI Mode (OFF/BASIC/ENHANCED) is disabled while Zeli is selected')

    const setupBody = await page.locator('body').innerText()
    log(/Zeli is ready/i.test(setupBody),
      'backend reports Zeli is configured and ready', 'zeli status rendered')
    await shot(page, '01-zeli-selected.png')

    // ── 3. Real whole-lesson generation ─────────────────────────────────────
    await page.getByRole('button', { name: /generate lesson plans/i }).click()
    await page.locator('[data-lesson-workspace]').waitFor({ timeout: 300000 })
    await page.waitForTimeout(1500)
    await shot(page, '02-generated.png')

    const list = await apiGet(page, '/api/generation/lessons')
    const all = list.body?.lesson_plans || []
    log(all.length >= 1, 'generation produced lesson plans', `${all.length} lesson(s)`)
    const lesson = all[0] || {}
    log(lesson.generation_method === 'zeli',
      'the persisted lesson records generation_method=zeli',
      String(lesson.generation_method))
    log(lesson.ai_generated === true, 'the lesson records AI-generated content')
    log(Boolean(lesson.ai_provider),
      'the persisted provenance names the real provider (id)',
      String(lesson.ai_provider))
    log(Boolean((lesson.starter_activity || '').trim()),
      'Zeli wrote the starter', String(lesson.starter_activity || '').slice(0, 50))
    log(Boolean((lesson.assessment || '').trim()),
      'Zeli wrote the assessment', String(lesson.assessment || '').slice(0, 50))
    log(Boolean((lesson.conclusion || '').trim()),
      'Zeli wrote the plenary/conclusion')

    const body = await page.locator('body').innerText()
    log(/generated by Zeli/i.test(body),
      'the result tells the teacher Zeli generated the lessons')
    log(!/all lessons generated deterministically/i.test(body),
      'no deterministic-fallback claim on a Zeli run')
    // Teacher surface must not leak provider/model/API internals.
    const lowered = body.toLowerCase()
    for (const bad of ['groq', 'gpt-oss', 'openai/gpt', 'api key', 'rate_limit']) {
      log(!lowered.includes(bad), `teacher surface hides "${bad}"`)
    }

    // ── 4. Switching back restores the existing options ─────────────────────
    await page.goto(`${WEB}/generate/${schemeId.schemeId}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
    // Once a job exists the workspace takes over and the setup surface is
    // hidden (§15). "Start New Generation" is the real teacher path back to
    // configuration, where the persisted method choice must still be Zeli.
    // Wait for the page's async status restore first: either the setup selector
    // is already visible, or the workspace exposes the Start New Generation
    // button. Reading count() immediately after domcontentloaded races the load.
    const startNew = page.getByRole('button', { name: /start new generation/i })
    const zeliSelector = page.locator('[data-generation-method="zeli"]')
    await page.waitForFunction(
      () => Boolean(document.querySelector('[data-generation-method="zeli"]'))
        || Array.from(document.querySelectorAll('button'))
          .some((b) => /start new generation/i.test(b.textContent || '')),
      null,
      { timeout: 90000 },
    )
    if (await startNew.count()) {
      await startNew.click()
    }
    await zeliSelector.waitFor({ timeout: 60000 })
    log((await page.locator('[data-generation-method="zeli"]').getAttribute('aria-pressed')) === 'true',
      'the Zeli choice persists across a reload')
    await page.locator('[data-generation-method="standard"]').click()
    await page.waitForTimeout(500)
    log(!(await page.locator('#cfg-ai-mode').isDisabled()),
      'choosing Standard re-enables OFF/BASIC/ENHANCED')
    const options = await page.locator('#cfg-ai-mode option').allInnerTexts()
    log(options.some((o) => /^OFF/.test(o.trim()))
      && options.some((o) => /^BASIC/.test(o.trim()))
      && options.some((o) => /^ENHANCED/.test(o.trim())),
      'existing OFF / BASIC / ENHANCED options are intact', options.join(' | '))
    await shot(page, '03-standard-restored.png')
  } catch (err) {
    log(false, 'journey threw', err && err.message ? err.message : String(err))
    await shot(page, 'ERROR.png').catch(() => {})
  } finally {
    if (pageErrors.length) console.log(`[diag] page errors: ${JSON.stringify(pageErrors)}`)
    console.log(`\n${'='.repeat(72)}\nZELI METHOD PASS: ${pass} passed, ${fail} failed`)
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n'))
    await browser.close()
  }
  process.exit(fail === 0 ? 0 : 1)
})()
