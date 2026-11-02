/**
 * UX editing acceptance: lesson-config prefill/blank overrides, lesson save
 * rollback/conflict, weekly-plan draft/conflict. Disposable local data only.
 *
 * Env: UX_WEB_URL, UX_API_URL, UX_TOKEN, UX_USER, UX_LESSON_ID, UX_PLAN_ID
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const WEB = process.env.UX_WEB_URL || 'http://127.0.0.1:3100'
const API = process.env.UX_API_URL || 'http://127.0.0.1:8100'
const TOKEN = process.env.UX_TOKEN || ''
const USER = JSON.parse(process.env.UX_USER || '{}')
const LESSON_ID = process.env.UX_LESSON_ID || ''
const PLAN_ID = process.env.UX_PLAN_ID || 'wp-ux-fixture'
const PDF = path.resolve(__dirname, '..', '..', 'backend', 'real_documents', 'BASIC 6 TERM 1.pdf')
const results = []

function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

async function api(pathname, options = {}) {
  const response = await fetch(`${API}${pathname}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  const text = await response.text()
  let body = null
  try { body = text ? JSON.parse(text) : null } catch { body = text }
  return { status: response.status, body, headers: response.headers }
}

async function lesson() {
  return (await api(`/api/generation/lessons/${LESSON_ID}`)).body
}

async function plan() {
  return (await api(`/api/weekly-plans/${PLAN_ID}`)).body
}

async function uploadScheme() {
  const bytes = fs.readFileSync(PDF)
  const form = new FormData()
  form.append('file', new Blob([bytes], { type: 'application/pdf' }), `ux-config-${Date.now()}.pdf`)
  const response = await fetch(`${API}/api/documents/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${TOKEN}` },
    body: form,
  })
  if (!response.ok) throw new Error(`upload ${response.status}`)
  return response.json()
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await context.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: TOKEN, user: USER })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))

  // ── A. Lesson-config prefill, explicit blank, restore ───────────────────
  const scheme = await uploadScheme()
  await page.goto(`${WEB}/review/${scheme.scheme_id}`, { waitUntil: 'domcontentloaded' })
  const openConfig = page.getByRole('button', { name: /Configure lesson rubrics/i }).first()
  await openConfig.waitFor({ timeout: 30000 })
  await openConfig.click()

  const teacher = page.getByLabel("Teacher's name")
  const school = page.getByLabel('School name')
  await teacher.waitFor({ timeout: 10000 })
  const prefilledTeacher = await teacher.inputValue()
  const prefilledSchool = await school.inputValue()
  record('profile name prefills blank lesson config', prefilledTeacher === USER.full_name, prefilledTeacher)
  record('profile school prefills blank lesson config', prefilledSchool === 'UX Test School', prefilledSchool)

  await teacher.fill('Saved Teacher')
  await page.getByRole('button', { name: 'Save & apply' }).click()
  await page.getByText('Lesson settings saved.').waitFor({ timeout: 20000 })
  await page.waitForTimeout(300)
  await openConfig.click()
  await page.getByLabel("Teacher's name").waitFor({ timeout: 10000 })
  const savedTeacher = await page.getByLabel("Teacher's name").inputValue()
  record('server-saved value wins over profile', savedTeacher === 'Saved Teacher', savedTeacher)

  await page.getByLabel("Teacher's name").fill('')
  await page.getByRole('button', { name: 'Save & apply' }).click()
  await page.getByText('Lesson settings saved.').waitFor({ timeout: 20000 })
  await page.waitForTimeout(300)
  await openConfig.click()
  await page.getByLabel("Teacher's name").waitFor({ timeout: 10000 })
  const blankTeacher = await page.getByLabel("Teacher's name").inputValue()
  record('deliberately cleared value stays blank on reopen', blankTeacher === '', blankTeacher)

  const restore = page.getByRole('button', { name: /Use my name from profile/i })
  const restoreVisible = await restore.isVisible().catch(() => false)
  if (restoreVisible) {
    await restore.click()
    const restored = await page.getByLabel("Teacher's name").inputValue()
    record('restore-default action reapplies the profile value', restored === USER.full_name, restored)
  } else {
    record('restore-default action reapplies the profile value', false, 'button not visible')
  }
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Cancel' }).first().click().catch(() => {})
  await page.getByRole('button', { name: 'Cancel' }).first().click().catch(() => {})

  // ── B. Lesson save success, failure, retry, conflict ───────────────────
  await page.goto(`${WEB}/lessons/${LESSON_ID}`, { waitUntil: 'domcontentloaded' })
  const topic = page.getByLabel('Lesson Topic')
  await topic.waitFor({ timeout: 30000 })
  await topic.fill('Browser save one')
  await page.getByRole('button', { name: /Save Changes/i }).click()
  await page.getByText('Lesson saved.').waitFor({ timeout: 20000 })
  const savedServer = await lesson()
  record('lesson save reconciles with the server', savedServer.lesson_topic === 'Browser save one')

  await page.route(`**/api/generation/lessons/${LESSON_ID}`, async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Traceback: psycopg failure' }),
      })
      return
    }
    await route.continue()
  })
  await topic.fill('Unsaved work must survive')
  await page.getByRole('button', { name: /Save Changes/i }).click()
  await page.getByText('Lesson was not saved').waitFor({ timeout: 20000 })
  const kept = await topic.inputValue()
  const friendly = await page.getByText(/temporarily unavailable|Something went wrong/i).first().isVisible().catch(() => false)
  record('failed lesson save preserves the teacher work', kept === 'Unsaved work must survive', kept)
  record('failed lesson save shows friendly text', friendly)

  await page.unroute(`**/api/generation/lessons/${LESSON_ID}`)
  await page.getByRole('button', { name: 'Try again' }).click()
  let retriedTopic = ''
  for (let i = 0; i < 30; i += 1) {
    retriedTopic = (await lesson()).lesson_topic || ''
    if (retriedTopic === 'Unsaved work must survive') break
    await page.waitForTimeout(300)
  }
  record('lesson retry repeats the save and succeeds', retriedTopic === 'Unsaved work must survive', retriedTopic)

  // External update after the editor loaded.
  const current = await lesson()
  await api(`/api/generation/lessons/${LESSON_ID}`, {
    method: 'PUT',
    headers: { 'If-Match': current.updated_at },
    body: JSON.stringify({ lesson_topic: 'Server newer topic' }),
  })
  await topic.fill('My stale edit')
  await page.getByRole('button', { name: /Save Changes/i }).click()
  await page.getByText('This lesson changed on the server', { exact: true }).waitFor({ timeout: 20000 })
  record('stale lesson save is blocked with a conflict', (await lesson()).lesson_topic === 'Server newer topic')
  await page.getByRole('button', { name: 'Overwrite latest with my draft' }).click()
  let overwritten = ''
  for (let i = 0; i < 30; i += 1) {
    overwritten = (await lesson()).lesson_topic || ''
    if (overwritten === 'My stale edit') break
    await page.waitForTimeout(300)
  }
  record('explicit overwrite replaces the latest lesson', overwritten === 'My stale edit', overwritten)
  await page.getByRole('button', { name: 'Load latest version' }).click().catch(() => {})
  await page.waitForTimeout(500)
  const latestTopic = await topic.inputValue()
  record('load-latest shows the overwritten server value', latestTopic === 'My stale edit', latestTopic)

  // ── C. Weekly-plan edit, draft, conflict ───────────────────────────────
  await page.goto(`${WEB}/weekly-plans/${PLAN_ID}`, { waitUntil: 'domcontentloaded' })
  const starter = page.getByLabel('Starter').first()
  await starter.waitFor({ timeout: 30000 })
  const originalStarter = await starter.inputValue()
  record('weekly plan loads saved values', originalStarter === 'Original starter', originalStarter)

  await starter.fill('Browser starter')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByText('Changes saved', { exact: true }).waitFor({ timeout: 20000 })
  const savedPlan = await plan()
  record('weekly plan save persists to the server',
    savedPlan.plan.subjects[0].day_plans[0].starter === 'Browser starter')

  const reflection = page.getByLabel('Reflection').first()
  await reflection.fill('Draft reflection')
  await page.waitForTimeout(1200)
  await page.reload({ waitUntil: 'domcontentloaded' })
  const recovered = await page.getByText(/We found your unsaved work/).first()
    .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false)
  record('weekly plan draft recovers after refresh', recovered)
  if (recovered) {
    await page.getByRole('button', { name: 'Continue draft' }).click()
    record('recovered weekly edit is restored',
      (await page.getByLabel('Reflection').first().inputValue()) === 'Draft reflection')
  }

  // External update, then a stale save from this page.
  const latestPlan = await plan()
  await api(`/api/weekly-plans/${PLAN_ID}`, {
    method: 'PUT',
    headers: { 'If-Match': latestPlan.version },
    body: JSON.stringify({ subjects: [{
      index: 0,
      day_plans: [{ index: 0, starter: 'External starter' }],
    }] }),
  })
  await page.getByLabel('Reflection').first().fill('Still my old edit')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByText('This weekly plan changed on the server', { exact: true }).waitFor({ timeout: 20000 })
  const afterConflict = await plan()
  record('stale weekly save is blocked with a conflict',
    afterConflict.plan.subjects[0].day_plans[0].starter === 'External starter')
  await page.getByRole('button', { name: 'Overwrite latest with my draft' }).click()
  let weeklyOverwritten = ''
  for (let i = 0; i < 30; i += 1) {
    weeklyOverwritten = (await plan()).plan.subjects[0].day_plans[0].reflection || ''
    if (weeklyOverwritten === 'Still my old edit') break
    await page.waitForTimeout(300)
  }
  record('explicit overwrite replaces the latest weekly plan',
    weeklyOverwritten === 'Still my old edit', weeklyOverwritten)
  await page.waitForTimeout(500)
  record('weekly overwrite keeps the server starter value',
    (await page.getByLabel('Starter').first().inputValue()) === 'External starter')

  record('no uncaught page errors',
    errors.filter((text) => !/Failed to load resource|409|500/.test(text)).length === 0,
    errors.slice(0, 2).join(' | '))

  await browser.close()
  const failed = results.filter((item) => !item.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
}).finally(() => setTimeout(() => process.exit(process.exitCode || 0), 500))
