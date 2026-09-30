/**
 * Production WAPEF-preservation check under a real Zeli (Groq) rewrite.
 *
 * The generate-time WAPEF race left the four WAPEF fields empty on the
 * production lessons, so "Zeli preserved WAPEF" could not be proven there.
 * This script sets the four WAPEF fields on the WORKSPACE (the surface the
 * persistence journey proved authoritative), saves, then runs ONE real Zeli
 * rewrite on the review page and confirms the four WAPEF fields are exactly
 * what the teacher set them to.
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

  try {
    // ── login ─────────────────────────────────────────────────────────────
    await page.goto(`${WEB}/login`, { waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.locator('#teacher-email').waitFor({ timeout: 60000 })
    await page.locator('#teacher-email').fill(state.email)
    await page.locator('#teacher-password').fill(state.password)
    await page.getByRole('button', { name: /^Sign in$/ }).click()
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 120000 })

    const lesson = await apiGet(page, `/api/generation/lessons/${state.lessonId}`)
    const jobId = lesson.body.job_id
    log(Boolean(jobId), 'resolved the lesson job', jobId)

    // ── 1. Set the four WAPEF fields through the app's own lesson-save
    // boundary (the same PUT the workspace Save issues). ───────────────────
    const opts = (await apiGet(page, '/api/generation/wapef/options')).body || {}
    const picks = {
      deepHope: opts.deep_hopes[1] || opts.deep_hopes[0],
      storyline: opts.storylines[1] || opts.storylines[0],
      godsStory: opts.gods_story[1] || opts.gods_story[0],
    }
    log(Boolean(picks.deepHope), 'real WAPEF options resolved', picks.deepHope)

    const putRes = await page.evaluate(async ({ apiBase, id, picks, through }) => {
      const token = sessionStorage.getItem('teachflow_token')
      const res = await fetch(`${apiBase}/api/generation/lessons/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          wapef_deep_hope: picks.deepHope,
          wapef_storyline: picks.storyline,
          wapef_gods_story: picks.godsStory,
          wapef_through_lines: through,
        }),
      })
      let body = null
      try { body = await res.json() } catch { /* non-JSON */ }
      return { status: res.status, body }
    }, { apiBase: API, id: state.lessonId, picks, through: opts.through_lines.slice(0, 2) })
    log(putRes.status === 200, 'WAPEF baseline stored through the lesson-save boundary', `status=${putRes.status}`)

    let stored = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    for (let i = 0; i < 12 && !(stored.wapef_deep_hope); i += 1) {
      await sleep(2000)
      stored = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    }
    log(stored.wapef_deep_hope === picks.deepHope,
      'the stored Deep Hope is what the teacher set',
      (stored.wapef_deep_hope || '').slice(0, 40))
    log(stored.wapef_storyline === picks.storyline,
      'the stored Storyline is what the teacher set', stored.wapef_storyline)
    log(stored.wapef_gods_story === picks.godsStory,
      "the stored God's Story is what the teacher set", stored.wapef_gods_story)
    log((stored.wapef_through_lines || []).length >= 2,
      'the stored Through lines are what the teacher set',
      JSON.stringify(stored.wapef_through_lines || []))

    const wapefSnapshot = {
      deep: stored.wapef_deep_hope,
      story: stored.wapef_storyline,
      gods: stored.wapef_gods_story,
      through: JSON.stringify(stored.wapef_through_lines || []),
    }
    const assessmentBefore = stored.assessment

    // ── 3. One real Zeli rewrite on the review page ───────────────────────
    await page.goto(`${WEB}/lessons/${state.lessonId}`, { waitUntil: 'domcontentloaded', timeout: 180000 })
    await page.locator('textarea[aria-label="Assessment"]').waitFor({ timeout: 120000 })
    for (let i = 0; i < 20; i += 1) {
      const got = await page.evaluate(() =>
        document.querySelector('textarea[aria-label="Assessment"]')?.value || '')
      if (got) break
      await sleep(1500)
    }

    const qBefore = (await apiGet(page, '/api/auth/my-plan')).body
    await page.locator('section[aria-label="Assessment"]')
      .getByRole('button', { name: 'Suggest another version' }).click()
    await page.getByText('Zeli rewrote this section').waitFor({ timeout: 240000 })
    await page.getByRole('button', { name: 'Save Changes' }).click()
    await page.getByText('Saved', { exact: true }).waitFor({ timeout: 90000 }).catch(() => {})

    const after = (await apiGet(page, `/api/generation/lessons/${state.lessonId}`)).body
    const qAfter = (await apiGet(page, '/api/auth/my-plan')).body

    log(Boolean(after.assessment) && after.assessment !== assessmentBefore,
      'the real Zeli rewrite changed the assessment on production',
      (after.assessment || '').slice(0, 40))
    log(after.wapef_deep_hope === wapefSnapshot.deep,
      'the Deep Hope survived the production Zeli rewrite',
      (after.wapef_deep_hope || '').slice(0, 40))
    log(after.wapef_storyline === wapefSnapshot.story,
      'the Storyline survived the production Zeli rewrite', after.wapef_storyline)
    log(after.wapef_gods_story === wapefSnapshot.gods,
      "God's Story survived the production Zeli rewrite", after.wapef_gods_story)
    log(JSON.stringify(after.wapef_through_lines || []) === wapefSnapshot.through,
      'the Through lines survived the production Zeli rewrite',
      JSON.stringify(after.wapef_through_lines || []))
    log(qAfter.ai_quota_used === qBefore.ai_quota_used + 1,
      'the production rewrite consumed exactly one AI unit',
      `${qBefore.ai_quota_used} -> ${qAfter.ai_quota_used}`)

    const body = await page.locator('body').innerText()
    log(!/groq|gemini|openai|gpt-oss|rate_limit/i.test(body),
      'no provider/API term anywhere on the production teacher surface')
  } catch (err) {
    log(false, 'check threw', err && err.message ? err.message : String(err))
    await page.screenshot({ path: path.join(OUT, 'prod-wapef-ERROR.png') }).catch(() => {})
  } finally {
    console.log(`\n${'='.repeat(72)}\nPROD WAPEF CHECK: ${pass} passed, ${fail} failed`)
    await browser.close()
  }
  process.exit(fail === 0 ? 0 : 1)
})()
