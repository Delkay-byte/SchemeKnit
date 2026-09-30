/**
 * SchemeKnit Zeli (Groq) browser journey — success and failure passes.
 *
 * Proves the teacher-facing AI assistant, end to end, on the real app against
 * the real backend:
 *
 * SUCCESS PASS (default, TF_ZELI_MODE=success)
 *   sign up a teacher -> school -> upload the real Computing scheme
 *     -> Approved WAPEF Plan -> preview -> set the four WAPEF fields
 *     -> AI Mode OFF -> GENERATE (the deterministic 4-layer engine owns the
 *        lesson; Zeli touches nothing here)
 *     -> the lesson exists with its phased structure and NO ai_provider
 *     -> open the /lessons/{id} review page
 *     -> status reads "Zeli available"
 *     -> "Suggest another version" on Assessment
 *        * Zeli rewrites ONLY that section (starter, plenary, WAPEF fields,
 *          indicators and topic are untouched)
 *        * one monthly AI unit consumed
 *     -> REJECT by reloading: the deterministic assessment is back, the
 *        suggestion banner is gone, no extra unit consumed
 *     -> suggest again -> Save Changes
 *     -> leave for /lessons, return, reload: the Zeli rewrite persists
 *     -> the review page never shows a provider/model/API term
 *     -> writes state.json for the failure pass
 *
 * FAILURE PASS (TF_ZELI_MODE=failure)
 *   Requires the backend restarted with a broken GROQ_API_KEY
 *   (e.g. GROQ_API_KEY=gsk-invalid zeli-cannot-run python -m uvicorn ...).
 *   logs the success-pass teacher back in -> review page
 *     -> "Suggest another version"
 *        * the teacher sees ONLY "Zeli could not rewrite this section right
 *          now. Your existing content was preserved." (no 429 / auth / model
 *          / provider / stack language)
 *        * the deterministic content is byte-for-byte intact
 *        * NO AI unit is consumed
 *        * the page is still fully editable and Save still works
 *
 * Usage:
 *   node e2e/zeli-groq-journey.js                 # success pass
 *   TF_ZELI_MODE=failure node e2e/zeli-groq-journey.js
 *
 * Requires: backend on :8000 and the frontend (`next start` or `next dev`)
 * on :3000. The success pass needs a WORKING GROQ_API_KEY on the backend.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3000').replace(/\/$/, '')
const API = (process.env.TF_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const ROOT = path.join(__dirname, '..', '..')
const SCHEME = process.env.TF_SCHEME_FILE
  ? path.resolve(process.env.TF_SCHEME_FILE)
  : path.join(ROOT, 'backend', 'tests', 'fixtures', 'remediation',
    'bs7_code_only_indicators_scheme.docx')
const OUT = path.join(__dirname, 'zeli-groq-journey')
fs.mkdirSync(OUT, { recursive: true })
const STATE = path.join(OUT, 'state.json')

const MODE = (process.env.TF_ZELI_MODE || 'success').toLowerCase()
const STAMP = Date.now()
const EMAIL = MODE === 'failure' && fs.existsSync(STATE)
  ? JSON.parse(fs.readFileSync(STATE, 'utf8')).email
  : `zeli.teacher.${STAMP}@schemeknit.test`
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

/**
 * Wait until React is hydrated AND STABLE: fill() before hydration is
 * silently wiped when the app swaps in the hydrated tree. The probe value
 * must SURVIVE a settle window.
 */
async function waitHydrated(page, probe = '#signup-name', timeout = 30000) {
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
      await sleep(1500)
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

/** Authenticated request from inside the page (uses the real session token). */
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
  await page.locator('#signup-name').fill('Zeli Teacher')
  await page.locator('#signup-email').fill(EMAIL)
  await page.locator('#signup-password').fill(PASSWORD)
  await page.locator('#signup-confirm').fill(PASSWORD)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 60000 })
}

async function setSchoolInSettings(page) {
  await page.goto(`${WEB}/settings`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  const input = page.locator('#profile-school')
  await input.waitFor({ timeout: 30000 })
  await waitHydrated(page, '#profile-school')
  await input.fill(SCHOOL)
  await page.getByRole('button', { name: /save profile/i }).click()
  await page.waitForTimeout(1500)
  return input.inputValue().catch(() => '')
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
  await page.waitForURL(/\/review\//, { timeout: 90000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  return page.url().split('/review/')[1].split(/[/?#]/)[0]
}

/** Select the Approved WAPEF Plan and run a short allocation preview. */
async function configureWapef(page, { perWeek }) {
  await page.getByRole('button', { name: /approve & configure/i }).last().click()
  await page.waitForURL(/\/generate\//, { timeout: 60000 })
  await page.waitForLoadState('networkidle').catch(() => {})

  const sel = page.locator('#cfg-template')
  await sel.waitFor({ timeout: 30000 })
  await page.waitForFunction(() => {
    const el = document.querySelector('#cfg-template')
    return el && el.options.length >= 2
  }, { timeout: 30000 }).catch(() => {})
  const optionLabels = await sel.locator('option').allInnerTexts()
  const wapefLabel = optionLabels.find((o) => /Approved WAPEF Plan/i.test(o))
  await sel.selectOption({ label: wapefLabel })
  await page.waitForFunction(() => {
    const el = document.querySelector('#cfg-template')
    return el && el.value === 'tpl-wapef-approved-plan'
  }, { timeout: 15000 })

  // AI Mode OFF: this lesson comes from the deterministic engine. Zeli is
  // invited later, on the review page, one section at a time.
  await page.locator('#cfg-ai-mode').selectOption('OFF')

  await page.locator('#cfg-term-start').fill('2026-09-14')
  await page.locator('#cfg-term-end').fill('2026-09-25')
  await page.locator('#cfg-lessons-per-week').fill(perWeek)
  await page.getByRole('button', { name: /preview allocation/i }).click()
  await page.locator('[data-lesson-review]').waitFor({ timeout: 90000 })
  await page.locator('select[id^="wapef-deep-hope-"]').first().waitFor({ timeout: 30000 })
  return { wapefLabel, optionLabels }
}

/** Read the approved option lists so the journey selects REAL values. */
async function wapefOptions(page) {
  const res = await apiGet(page, '/api/generation/wapef/options')
  return res.status === 200 ? res.body : null
}

/** Set all four WAPEF fields on the first lesson row, with 2+ Through lines. */
async function setWapefOnRow(page, opts, picks) {
  const deepHope = page.locator('select[id^="wapef-deep-hope-"]').first()
  await deepHope.selectOption({ label: picks.deepHope })
  await page.locator('select[id^="wapef-storyline-"]').first().selectOption({ label: picks.storyline })
  await page.locator('select[id^="wapef-gods-story-"]').first().selectOption({ label: picks.godsStory })

  const rowScope = deepHope.locator('xpath=ancestor::div[contains(@class,"rounded-md border")]')
  const chips = rowScope.locator('button[type="button"]')
  const total = await chips.count()
  for (let i = 0; i < Math.min(2, total); i += 1) await chips.nth(i).click()
  const selected = []
  for (let i = 0; i < Math.min(2, total); i += 1) {
    selected.push((await chips.nth(i).innerText()).trim())
  }
  return selected
}

async function generate(page) {
  await page.getByRole('button', { name: /confirm & generate/i }).click()
  await page.locator('[data-lesson-workspace]').waitFor({ timeout: 180000 })
  await page.waitForTimeout(1500)
}

/** The authoritative server view of the lesson (the database, not the DOM). */
async function fetchLesson(page, lessonId) {
  const res = await apiGet(page, `/api/generation/lessons/${lessonId}`)
  return res.body || {}
}

/** Monthly AI units consumed so far for this teacher. */
async function quotaUsed(page) {
  const res = await apiGet(page, '/api/auth/my-plan')
  const b = res.body || {}
  return {
    used: b.ai_quota_used ?? b.ai_credits_used ?? null,
    remaining: b.ai_quota_remaining ?? null,
    limit: b.ai_quota_limit ?? b.ai_credits ?? null,
    status: res.status,
  }
}

/** Read the review page's editable section text exactly as the teacher sees it. */
async function readReview(page) {
  return page.evaluate(() => {
    const val = (sel) => {
      const el = document.querySelector(sel)
      return el && 'value' in el ? el.value : null
    }
    return {
      intro: val('textarea[aria-label="Introduction / Starter"]'),
      assessment: val('textarea[aria-label="Assessment"]'),
      conclusion: val('textarea[aria-label="Conclusion / Reflection"]'),
    }
  })
}

/** The review page must never name the provider, model or any API term. */
async function providerLeakScan(page) {
  const body = (await page.locator('body').innerText()).toLowerCase()
  const leaks = ['groq', 'gemini', 'openai', 'gpt-oss', 'gpt-4', 'rate_limit',
    'rate limit', 'malformed', 'api key', 'api_key', '429', '503', '502',
    'json schema', 'structured output', 'temperature', 'retry']
  for (const bad of leaks) {
    log(!body.includes(bad), `review page hides provider/API term "${bad}"`)
  }
}

async function waitForReviewPage(page, lessonId) {
  await page.goto(`${WEB}/lessons/${lessonId}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.locator('textarea[aria-label="Assessment"]').waitFor({ timeout: 120000 })
  // Cold fetch: let the lesson payload land before reading anything.
  for (let i = 0; i < 20; i += 1) {
    const got = await readReview(page)
    if (got.assessment !== null && got.assessment !== '') break
    await sleep(1500)
  }
}

/** Click "Suggest another version" on a section and wait for Zeli's answer. */
async function suggest(page, sectionLabel, { expectSuccess = true } = {}) {
  const sec = page.locator(`section[aria-label="${sectionLabel}"]`)
  await sec.getByRole('button', { name: 'Suggest another version' }).click()
  if (expectSuccess) {
    await page.getByText('Zeli rewrote this section').waitFor({ timeout: 180000 })
  } else {
    await page.getByText('Zeli could not rewrite this section right now')
      .waitFor({ timeout: 180000 })
  }
}

async function successPass(page) {
  // ── 1. Teacher account + school ─────────────────────────────────────────
  await signup(page)
  log(true, 'fresh teacher account created', EMAIL)
  const schoolShown = await setSchoolInSettings(page)
  log(schoolShown === SCHOOL, 'school stored on the teacher profile', schoolShown)

  // ── 2. Real scheme through the real upload surface ──────────────────────
  if (!fs.existsSync(SCHEME)) throw new Error(`scheme fixture missing: ${SCHEME}`)
  const schemeId = await uploadScheme(page)
  log(true, 'real Computing scheme uploaded and extracted', `scheme=${schemeId}`)
  await shot(page, '01-review.png')

  // ── 3. WAPEF template + allocation preview ──────────────────────────────
  const { wapefLabel } = await configureWapef(page, { perWeek: '2' })
  log(/Approved WAPEF Plan/i.test(wapefLabel || ''),
    'Approved WAPEF Plan selected; AI Mode left OFF (deterministic)', wapefLabel)
  await shot(page, '02-generate-wapef.png')

  const opts = await wapefOptions(page)
  if (!opts || !opts.deep_hopes?.length) throw new Error('WAPEF options unavailable')
  const picks = {
    deepHope: opts.deep_hopes[0],
    storyline: opts.storylines[0],
    godsStory: opts.gods_story[0],
  }
  const chosenThrough = await setWapefOnRow(page, opts, picks)
  log(chosenThrough.length >= 2,
    'more than one Through line selected before generation', chosenThrough.join(', '))
  await shot(page, '03-wapef-rows.png')

  // ── 4. Generate with the deterministic engine ───────────────────────────
  await generate(page)
  await shot(page, '04-workspace.png')

  const list = await apiGet(page, '/api/generation/lessons')
  const all = list.body?.lesson_plans || []
  log(all.length >= 1, 'generation produced a lesson', `${all.length} lesson(s)`)
  const lessonId = all[0].id
  const lesson = await fetchLesson(page, lessonId)

  // The deterministic 4-layer engine owns this lesson — Zeli is not co-author.
  log(!lesson.provenance?.ai_provider,
    'deterministic generation: no AI provider on the lesson',
    String(lesson.provenance?.ai_provider || ''))
  log(lesson.template_id === 'tpl-wapef-approved-plan',
    'the lesson keeps the WAPEF template identity', String(lesson.template_id))

  const activities = lesson.main_activities || []
  const phaseCount = activities.filter((a) => (a.description || '').trim()).length
  log(phaseCount >= 3,
    'the deterministic engine produced the phased structure',
    `${phaseCount} activities`)
  const objectives = lesson.learning_objectives || []
  log((lesson.indicators || []).length >= 1,
    'indicators came from the scheme', (lesson.indicators || []).join(', '))
  log(objectives.length >= 1 && objectives.every((o) => (o.description || '').trim()),
    'the deterministic engine produced learning objectives tied to the indicator',
    `${objectives.length} objective(s)`)
  const snap = {
    topic: lesson.lesson_topic,
    intro: lesson.introduction,
    assessment: lesson.assessment,
    conclusion: lesson.conclusion,
    indicators: JSON.stringify(lesson.indicators || []),
    deepHope: lesson.wapef_deep_hope,
    storyline: lesson.wapef_storyline,
    godsStory: lesson.wapef_gods_story,
    through: JSON.stringify(lesson.wapef_through_lines || []),
    activities: JSON.stringify(activities),
  }
  log(Boolean(snap.assessment), 'deterministic assessment exists before Zeli',
    (snap.assessment || '').slice(0, 50))

  const qBefore = await quotaUsed(page)
  log(qBefore.status === 200, 'plan/quota endpoint reachable',
    `used=${qBefore.used} remaining=${qBefore.remaining}`)

  // ── 5. Review page: Zeli is available ───────────────────────────────────
  await waitForReviewPage(page, lessonId)
  await shot(page, '05-review.png')
  const statusBody = (await page.locator('body').innerText())
  log(/Zeli available\b/.test(statusBody) && !/Zeli unavailable/.test(statusBody),
    'review page reports "Zeli available"')

  // ── 6. Suggest another version — only that section moves ────────────────
  const before = await readReview(page)
  log(before.assessment === snap.assessment,
    'the review page shows the deterministic assessment first')

  await suggest(page, 'Assessment')
  await shot(page, '06-zeli-rewrote.png')
  const after = await readReview(page)

  log(Boolean(after.assessment) && after.assessment !== before.assessment,
    'Zeli rewrote the assessment', (after.assessment || '').slice(0, 50))
  log(after.intro === before.intro, 'the starter is untouched by Zeli')
  log(after.conclusion === before.conclusion, 'the plenary is untouched by Zeli')

  // The database agrees nothing else moved — WAPEF, indicators, topic.
  const mid = await fetchLesson(page, lessonId)
  log(mid.wapef_deep_hope === snap.deepHope, "Zeli did not touch the Deep Hope")
  log(mid.wapef_storyline === snap.storyline, 'Zeli did not touch the Storyline')
  log(mid.wapef_gods_story === snap.godsStory, "Zeli did not touch God's Story")
  log(JSON.stringify(mid.wapef_through_lines || []) === snap.through,
    'Zeli did not touch the Through lines')
  log(JSON.stringify(mid.indicators || []) === snap.indicators,
    'Zeli did not touch the indicators')
  log(mid.lesson_topic === snap.topic, 'Zeli did not touch the topic')
  log(mid.introduction === snap.intro, 'Zeli did not touch the starter in the DB')
  log(mid.conclusion === snap.conclusion, 'Zeli did not touch the plenary in the DB')

  const qAfter1 = await quotaUsed(page)
  log(qAfter1.used === qBefore.used + 1,
    'one successful suggestion consumed exactly one AI unit',
    `${qBefore.used} -> ${qAfter1.used}`)

  // ── 7. Reject: reload, the deterministic content is back ────────────────
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.locator('textarea[aria-label="Assessment"]').waitFor({ timeout: 120000 })
  for (let i = 0; i < 20; i += 1) {
    const got = await readReview(page)
    if (got.assessment === snap.assessment) break
    await sleep(1500)
  }
  const rejected = await readReview(page)
  await shot(page, '07-rejected.png')
  log(rejected.assessment === snap.assessment,
    'rejecting the suggestion restores the deterministic assessment')
  log(/Zeli rewrote this section/.test(await page.locator('body').innerText()) === false,
    'the suggestion banner is gone after rejecting')

  const qAfterReject = await quotaUsed(page)
  log(qAfterReject.used === qBefore.used + 1,
    'rejecting the suggestion does not consume another unit (no re-consumption)',
    `${qAfterReject.used}`)

  // ── 8. Suggest again, then keep it ──────────────────────────────────────
  await suggest(page, 'Assessment')
  const kept = await readReview(page)
  log(Boolean(kept.assessment) && kept.assessment !== snap.assessment,
    'Zeli produced a second version', (kept.assessment || '').slice(0, 50))

  const qAfter2 = await quotaUsed(page)
  log(qAfter2.used === qBefore.used + 2,
    'the second suggestion consumed one more unit',
    `${qBefore.used} -> ${qAfter2.used}`)

  await page.getByRole('button', { name: 'Save Changes' }).click()
  await page.getByText('Saved').waitFor({ timeout: 60000 }).catch(() => {})
  const savedVisible = await page.getByText('Saved', { exact: true }).isVisible().catch(() => false)
  log(savedVisible, 'Save Changes reports the Zeli rewrite is stored')
  await shot(page, '08-saved.png')

  const stored = await fetchLesson(page, lessonId)
  log(stored.assessment === kept.assessment,
    'the saved lesson stores exactly the Zeli version')
  log(stored.wapef_deep_hope === snap.deepHope
    && stored.wapef_storyline === snap.storyline
    && stored.wapef_gods_story === snap.godsStory
    && JSON.stringify(stored.wapef_through_lines || []) === snap.through,
    'all four WAPEF fields survived the Zeli round-trip')
  log(stored.conclusion === snap.conclusion && stored.introduction === snap.intro,
    'the other sections are still the deterministic ones')

  // ── 9. Leave, return, reload — persistence ──────────────────────────────
  await page.goto(`${WEB}/lessons`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await waitForReviewPage(page, lessonId)
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 90000 })
  await page.locator('textarea[aria-label="Assessment"]').waitFor({ timeout: 120000 })
  for (let i = 0; i < 20; i += 1) {
    const got = await readReview(page)
    if (got.assessment === kept.assessment) break
    await sleep(1500)
  }
  const returned = await readReview(page)
  await shot(page, '09-after-return.png')
  log(returned.assessment === kept.assessment,
    'the Zeli rewrite survives leave -> return -> reload')

  const final = await fetchLesson(page, lessonId)
  log(final.assessment === kept.assessment,
    'the database still holds the Zeli version after the round-trip')

  // ── 10. No provider/API language anywhere on the teacher surface ────────
  await providerLeakScan(page)

  fs.writeFileSync(STATE, JSON.stringify({
    email: EMAIL, password: PASSWORD, lessonId,
    deterministicAssessment: snap.assessment,
    quotaUsed: qAfter2.used,
  }, null, 2))
  log(true, 'state written for the failure pass', STATE)
}

async function failurePass(page) {
  if (!fs.existsSync(STATE)) throw new Error(`run the success pass first: ${STATE}`)
  const state = JSON.parse(fs.readFileSync(STATE, 'utf8'))
  log(state.lessonId, 'failure pass reuses the success-pass teacher and lesson',
    state.email)

  // ── 1. Log the same teacher back in ─────────────────────────────────────
  await page.goto(`${WEB}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitHydrated(page, '#teacher-email')
  await page.locator('#teacher-email').fill(state.email)
  await page.locator('#teacher-password').fill(state.password)
  await page.getByRole('button', { name: /^Sign in$/ }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 60000 })

  // ── 2. The stored lesson is intact before Zeli tries ───────────────────
  await waitForReviewPage(page, state.lessonId)
  await shot(page, '10-failure-before.png')
  // Baseline = what is ACTUALLY stored now (the success pass saved a Zeli
  // rewrite). The guarantee under test is that a broken Zeli call changes
  // nothing, whatever the teacher currently has.
  const baseline = await fetchLesson(page, state.lessonId)
  const baselineAssessment = baseline.assessment
  const before = await readReview(page)
  log(before.assessment === baselineAssessment,
    'the stored assessment is intact before the broken Zeli call',
    (before.assessment || '').slice(0, 50))

  const qBefore = await quotaUsed(page)
  log(qBefore.status === 200, 'quota reachable before the broken call',
    `used=${qBefore.used}`)

  // ── 3. Zeli cannot run (bad key on the backend) — teacher-safe failure ──
  const t0 = Date.now()
  await suggest(page, 'Assessment', { expectSuccess: false })
  await shot(page, '11-failure-banner.png')
  console.log(`[diag] Zeli failure returned in ${Date.now() - t0}ms`)

  const body = await page.locator('body').innerText()
  log(/Zeli could not rewrite this section right now/.test(body)
    && /Your existing content was preserved/.test(body),
    'the teacher sees the calm Zeli failure message')
  // No provider/model/HTTP/auth language may leak into teacher copy.
  const leaks = ['groq', 'gemini', 'openai', 'gpt-oss', 'rate_limit', '429', '503',
    'unauthorized', 'invalid api key', 'api key', 'malformed', 'schema']
  for (const bad of leaks) {
    log(!body.toLowerCase().includes(bad), `failure copy hides "${bad}"`)
  }
  log(!/Zeli rewrote this section/.test(body),
    'no success banner on a failed suggestion')

  // ── 4. Nothing was consumed; nothing was changed ────────────────────────
  const after = await readReview(page)
  log(after.assessment === baselineAssessment,
    'the assessment is byte-for-byte what was stored before the failed call')
  log(after.intro === before.intro && after.conclusion === before.conclusion,
    'the other sections are untouched too')

  const qAfter = await quotaUsed(page)
  log(qAfter.used === qBefore.used,
    'a failed suggestion consumed ZERO AI units', `${qBefore.used} -> ${qAfter.used}`)

  const stored = await fetchLesson(page, state.lessonId)
  log(stored.assessment === baselineAssessment,
    'the database still holds the pre-failure assessment')

  // ── 5. The page is still a normal, editable lesson ──────────────────────
  const textarea = page.locator('textarea[aria-label="Assessment"]')
  await textarea.fill(`${baselineAssessment} Teacher edit after Zeli failed.`)
  await page.getByRole('button', { name: 'Save Changes' }).click()
  await page.getByText('Saved').waitFor({ timeout: 60000 }).catch(() => {})
  const savedVisible = await page.getByText('Saved', { exact: true }).isVisible().catch(() => false)
  log(savedVisible, 'the lesson is still editable and saves after a Zeli failure')
  await shot(page, '12-failure-saved.png')

  const final = await fetchLesson(page, state.lessonId)
  log(String(final.assessment).endsWith('Teacher edit after Zeli failed.'),
    'the teacher manual edit persisted past the Zeli failure')

  await providerLeakScan(page)
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const pageErrors = []
  const httpErrors = []
  page.on('pageerror', (e) => pageErrors.push(e.message))
  page.on('response', (r) => {
    if (r.status() >= 400) {
      httpErrors.push(`${r.status()} ${r.url().replace(WEB, '').slice(0, 120)}`)
    }
  })

  try {
    if (MODE === 'failure') {
      await failurePass(page)
    } else {
      await successPass(page)
    }
  } catch (err) {
    log(false, 'journey threw', err && err.message ? `${err.message}` : String(err))
    await shot(page, 'ERROR.png').catch(() => {})
  } finally {
    if (pageErrors.length) console.log(`[diag] page errors: ${JSON.stringify(pageErrors)}`)
    if (httpErrors.length) console.log(`[diag] http >=400: ${JSON.stringify(httpErrors.slice(0, 20))}`)
    console.log(`\n${'='.repeat(72)}\n${MODE.toUpperCase()} PASS: ${pass} passed, ${fail} failed`)
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n'))
    await browser.close()
  }
  process.exit(fail === 0 ? 0 : 1)
})()
