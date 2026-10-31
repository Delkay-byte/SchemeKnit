// Browser acceptance for the true resume path.
// A failed job with one persisted lesson and one planned-pending occurrence is
// staged in the isolated local DB. The teacher reloads, sees the recovery
// banner, and clicks Resume pending lessons. The same job is reused, the
// pending occurrence is generated, the existing lesson survives, and no
// duplicate rows appear.
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3100').replace(/\/$/, '')
const API = (process.env.TF_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const EMAIL = process.env.TF_TEACHER_EMAIL || ''
const PASSWORD = process.env.TF_TEACHER_PASSWORD || ''
const SCHEME = process.env.TF_SCHEME_ID || ''
const OUT = path.join(__dirname, '..', '..', 'backend', 'temp', 'resume-acceptance')
fs.mkdirSync(OUT, { recursive: true })

let pass = 0, fail = 0
function log(ok, label, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`)
  if (ok) pass++; else fail++
}

async function login(page) {
  await page.goto(`${WEB}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.getByText('Welcome back, teacher.').waitFor({ timeout: 30000 })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

async function apiGet(page, p) {
  return page.evaluate(async ({ apiBase, p }) => {
    const token = sessionStorage.getItem('teachflow_token')
    const res = await fetch(`${apiBase}${p}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: 'no-store',
    })
    let body = null
    try { body = await res.json() } catch { /* non-JSON */ }
    return { status: res.status, body }
  }, { apiBase: API, p })
}

;(async () => {
  if (!EMAIL || !PASSWORD || !SCHEME) {
    console.error('Set TF_TEACHER_EMAIL, TF_TEACHER_PASSWORD and TF_SCHEME_ID.')
    process.exit(2)
  }
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const pageErrors = []
  const httpErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('response', (r) => {
    if (r.status() >= 400) httpErrors.push(`${r.status()} ${r.url().replace(WEB, '').slice(0, 120)}`)
  })

  try {
    await login(page)
    log(true, 'teacher login succeeds', EMAIL)

    const before = await apiGet(page, `/api/generation/schemes/${SCHEME}/lessons`)
    const beforeLessons = before.body?.lesson_plans || []
    const existingOcc = beforeLessons[0]?.source_occurrence_id
    const existingTopic = beforeLessons[0]?.lesson_topic
    log(before.status === 200 && beforeLessons.length === 1,
      'partial batch starts with exactly one persisted lesson', `count=${beforeLessons.length}`)

    await page.goto(`${WEB}/generate/${SCHEME}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.locator('[data-generation-recovery]').waitFor({ timeout: 60000 })
    const banner = await page.locator('[data-generation-recovery]').innerText()
    log(/pending lessons/i.test(banner), 'recovery banner explains pending work', banner.replace(/\s+/g, ' ').slice(0, 140))
    const resumeButton = page.locator('[data-generation-resume]')
    log(await resumeButton.isVisible(), 'banner offers the explicit Resume action')
    log((await resumeButton.innerText()).includes('Resume pending lessons'),
      'resume action is named, not a bare Generate again')

    await resumeButton.click()
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-autopilot-outcome]')
      return el && /1 lesson plan generated/i.test(String(el.innerText || ''))
    }, null, { timeout: 120000 })
    log(true, 'resume reports one generated lesson in the result panel')

    await page.waitForFunction(() => !document.querySelector('[data-generation-recovery]'),
      null, { timeout: 60000 })
    log(true, 'recovery banner clears after the pending work completes')

    const after = await apiGet(page, `/api/generation/schemes/${SCHEME}/lessons`)
    const afterLessons = after.body?.lesson_plans || []
    const occs = afterLessons.map((l) => l.source_occurrence_id).filter(Boolean)
    log(afterLessons.length === 2, 'resume produced exactly two persisted lessons', `count=${afterLessons.length}`)
    log(new Set(occs).size === occs.length, 'no duplicate source occurrence was persisted', occs.join(' | '))
    log(afterLessons.some((l) => l.source_occurrence_id === existingOcc),
      'the pre-existing lesson was preserved')
    log(afterLessons.some((l) => l.source_occurrence_id === existingOcc && l.lesson_topic === existingTopic),
      'the existing lesson content was not overwritten')

    const status = await apiGet(page, `/api/generation/scheme/${SCHEME}/status`)
    log(status.body?.status === 'completed', 'the same job reaches completed status', status.body?.status)
    log(status.body?.can_resume === false && (status.body?.resumable_occurrence_ids || []).length === 0,
      'no resumable occurrences remain')

    log(pageErrors.length === 0, 'no uncaught page errors', pageErrors.slice(0, 2).join(' | '))
    log(httpErrors.length === 0, 'no HTTP 4xx/5xx during resume', httpErrors.slice(0, 3).join(' | '))
    await page.screenshot({ path: path.join(OUT, 'resume-complete.png'), fullPage: false }).catch(() => {})
  } catch (e) {
    log(false, 'journey completed', e.message.split('\n')[0].slice(0, 220))
    await page.screenshot({ path: path.join(OUT, '99-failure.png'), fullPage: false }).catch(() => {})
  } finally {
    await browser.close()
  }

  console.log(`\n${pass} passed, ${fail} failed — artefacts in ${OUT}`)
  process.exit(fail ? 1 : 0)
})()
