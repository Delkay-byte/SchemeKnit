/**
 * Phase 2 remediation browser acceptance (PART AA / U):
 *
 *  - Phase 2 · Main Learning is editable (activity text + duration)
 *  - edit → save → reload preserves the exact activities
 *  - add / remove activity, change duration all persist
 *  - "Suggest Main Learning" either inserts structured activities or shows a
 *    calm, teacher-safe warning — never a raw provider diagnostic
 *  - after an AI failure the existing activities are untouched and the teacher
 *    can keep editing manually
 *  - Download DOCX / PDF deliver real binary bytes (or a controlled, meaningful
 *    PDF environment limitation)
 *
 * Usage:
 *   node e2e/main-learning-download-acceptance.js
 * Env:
 *   TF_WEB_URL      frontend origin            (default http://localhost:3000)
 *   TF_API_URL      backend origin             (default http://localhost:8000)
 *   TF_TEACHER_EMAIL / TF_TEACHER_PASSWORD     a real entitled teacher
 *   TF_LESSON_ID    lesson to review (optional — else derived from TF_SCHEME_ID)
 *   TF_SCHEME_ID    scheme whose latest job's first lesson is reviewed
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { record, summary } = require('./report')

const WEB = process.env.TF_WEB_URL || 'http://localhost:3000'
const API = process.env.TF_API_URL || 'http://localhost:8000'
const OUT = path.join(__dirname, 'main-learning-download-acceptance')
const TEACHER = {
  email: process.env.TF_TEACHER_EMAIL || 'teacher@acceptance.test',
  password: process.env.TF_TEACHER_PASSWORD || 'TeacherPass123',
}
// PART 21: a realistic activity, never an internal/harness marker (see
// curriculum-workspace-acceptance.js).
const MARKER = `Learners sort the device pictures into manual and automatic groups ${Date.now().toString(36)}`

process.on('unhandledRejection', (err) => {
  const msg = String((err && err.message) || err)
  if (/TargetClosedError|Target page, context or browser has been closed/.test(msg)) return
  console.error('Unhandled rejection:', msg)
  process.exitCode = 1
})

async function resolveLessonId(request, token) {
  const headers = { Authorization: `Bearer ${token}` }
  if (process.env.TF_LESSON_ID) return process.env.TF_LESSON_ID
  const schemeId = process.env.TF_SCHEME_ID
  if (!schemeId) return null
  const status = await request
    .get(`${API}/api/generation/scheme/${schemeId}/status`, { headers })
    .then((r) => r.json())
    .catch(() => null)
  const jobId = status && status.id
  if (!jobId) return null
  const lessons = await request
    .get(`${API}/api/generation/${jobId}/lessons`, { headers })
    .then((r) => r.json())
    .catch(() => null)
  const first = lessons && lessons.lesson_plans && lessons.lesson_plans[0]
  return first && first.id
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ channel: process.env.TF_CHANNEL || 'chrome' })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
  })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(e.message))

  try {
    // 1. Login through the real form.
    await page.goto(`${WEB}/login`)
    await page.waitForTimeout(1500)
    await page.fill('input[type="email"]', TEACHER.email)
    await page.fill('input[type="password"]', TEACHER.password)
    await page.click('button[type="submit"]')
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
    record('login through the UI', true, page.url())

    // 2. Resolve the lesson to review.
    const token = await page.evaluate(() => sessionStorage.getItem('teachflow_token'))
    const lessonId = await resolveLessonId(context.request, token)
    if (!lessonId) {
      record('lesson available for review', false,
        'set TF_LESSON_ID or TF_SCHEME_ID to an existing generated scheme')
      throw new Error('no lesson to review')
    }
    record('lesson available for review', true, lessonId)

    await page.goto(`${WEB}/lessons/${lessonId}`)
    await page.waitForSelector('section[aria-label="Phase 2 Main Learning"]', { timeout: 30000 })

    // 3. Phase 2 must be editable.
    const act1 = page.getByLabel('Activity 1 description')
    const editable = (await act1.count()) > 0 && (await act1.first().isEditable().catch(() => false))
    record('Phase 2 Main Learning is editable', editable)

    // 4. Edit → Save → reload preserves the exact activity.
    await act1.first().fill(MARKER)
    const dur1 = page.getByLabel('Duration').first()
    if (await dur1.count()) await dur1.fill('13')
    await page.getByRole('button', { name: /save changes/i }).first().click()
    await page.waitForTimeout(2500)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForSelector('section[aria-label="Phase 2 Main Learning"]', { timeout: 30000 })
    const afterReload = await page.getByLabel('Activity 1 description').first().inputValue()
    record('manual edit persists after save + reload', afterReload === MARKER,
      JSON.stringify(afterReload).slice(0, 80))

    // 5. Add an activity → save → reload.
    await page.getByRole('button', { name: /add activity/i }).first().click()
    const countBefore = await page.getByLabel(/description$/i).count()
    const newAct = page.getByLabel(`Activity ${countBefore} description`).first()
    await newAct.fill(`${MARKER} two`)
    await page.getByRole('button', { name: /save changes/i }).first().click()
    await page.waitForTimeout(2500)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForSelector('section[aria-label="Phase 2 Main Learning"]', { timeout: 30000 })
    const countAfter = await page.getByLabel(/description$/i).count()
    record('added activity persists', countAfter >= countBefore,
      `${countBefore} -> ${countAfter}`)

    // 6. Remove an activity → save → reload.
    const removeBtns = page.getByRole('button', { name: /remove activity/i })
    await removeBtns.last().click()
    await page.getByRole('button', { name: /save changes/i }).first().click()
    await page.waitForTimeout(2500)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForSelector('section[aria-label="Phase 2 Main Learning"]', { timeout: 30000 })
    const countRemoved = await page.getByLabel(/description$/i).count()
    record('removed activity persists', countRemoved < countAfter,
      `${countAfter} -> ${countRemoved}`)

    // 7. Suggest Main Learning — success or calm failure, never raw diagnostics.
    const beforeAi = await page.getByLabel('Activity 1 description').first().inputValue()
    await page.getByRole('button', { name: /suggest main learning/i }).first().click()
    await page.waitForTimeout(12000)
    const body = await page.locator('body').innerText()
    const rawDiagnostic =
      /LIVE_ERROR|LIVE_RATE_LIMITED|malformed_json|empty_output|provider returned no usable content|state:\s*[A-Z_]+|Traceback|HTTP\s*4\d\d|HTTP\s*5\d\d/i.test(body)
    record('AI suggestion never exposes raw provider diagnostics', !rawDiagnostic)

    const aiInserted = /AI suggestion inserted by/i.test(body)
    const aiUnavailable =
      /AI suggestion (is )?(currently )?unavailable|AI is busy right now|AI suggestion unavailable right now/i.test(body)
    record('AI suggestion shows a defined outcome banner', aiInserted || aiUnavailable,
      aiInserted ? 'inserted' : aiUnavailable ? 'teacher-safe unavailable' : 'neither banner')

    if (aiInserted) {
      const structured = (await page.getByLabel(/description$/i).count()) > 0
      record('successful AI suggestion renders structured activities', structured)
      record('successful AI suggestion renders no raw JSON',
        !/[\[\{]"(phase|description|duration_minutes)"/.test(body))
    } else if (aiUnavailable) {
      const preserved = await page.getByLabel('Activity 1 description').first().inputValue()
      record('AI failure preserved the existing activities', preserved === beforeAi,
        JSON.stringify(preserved).slice(0, 80))
      // 8. Manual editing still works after an AI failure.
      await page.getByLabel('Activity 1 description').first().fill(`${MARKER} manual`)
      await page.getByRole('button', { name: /save changes/i }).first().click()
      await page.waitForTimeout(2500)
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.waitForSelector('section[aria-label="Phase 2 Main Learning"]', { timeout: 30000 })
      const manual = await page.getByLabel('Activity 1 description').first().inputValue()
      record('manual editing still works after AI failure', manual === `${MARKER} manual`)
    }

    await page.screenshot({ path: path.join(OUT, 'lesson-phase2-1440.png') })

    // 9. Downloads: DOCX + PDF must deliver real bytes via the real UI buttons.
    const schemeId = process.env.TF_SCHEME_ID
    if (schemeId) {
      await page.goto(`${WEB}/generate/${schemeId}`)
      await page.waitForTimeout(3000)

      const docx = await saveDownload(page, 'docx', () =>
        page.getByRole('button', { name: /download docx/i }).first().click())
      record('DOCX download reaches disk', docx.ok,
        docx.ok ? `${docx.suggested} (${docx.size} bytes)` : docx.error)
      if (docx.ok) {
        record('DOCX is a real file (PK zip signature)', docx.head.startsWith('PK'))
        record('DOCX filename ends in .docx', /\.docx$/i.test(docx.suggested), docx.suggested)
      }

      const pdf = await saveDownload(page, 'pdf', () =>
        page.getByRole('button', { name: /download pdf/i }).first().click(), 120000)
      if (pdf.ok) {
        record('PDF download reaches disk', true, `${pdf.suggested} (${pdf.size} bytes)`)
        record('PDF is a real file (%PDF- signature)', pdf.head === '%PDF')
        record('PDF filename ends in .pdf', /\.pdf$/i.test(pdf.suggested), pdf.suggested)
      } else {
        const body2 = await page.locator('body').innerText()
        const controlled = /PDF export requires a document converter|PDF conversion failed on the server/i.test(body2)
        record('PDF absence is a controlled, meaningful message (not "Failed to fetch")',
          controlled && !/Failed to fetch/i.test(body2))
      }
    } else {
      record('download step', true, 'skipped (set TF_SCHEME_ID to exercise downloads)')
    }

    record('no uncaught page exceptions', pageErrors.length === 0,
      pageErrors.slice(0, 3).join(' | '))
  } catch (e) {
    record('harness completed without throwing', false, e.message)
  } finally {
    try {
      await browser.close()
    } catch {
      /* already closed */
    }
  }

  const ok = summary('Phase 2 + downloads browser acceptance')
  process.exit(ok ? 0 : 1)
})()

async function saveDownload(page, label, action, timeout = 60000) {
  try {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout }),
      action(),
    ])
    const suggested = download.suggestedFilename()
    const dest = path.join(OUT, `${label}-${suggested}`)
    await download.saveAs(dest)
    const bytes = fs.readFileSync(dest)
    return {
      ok: true,
      suggested,
      path: dest,
      size: bytes.length,
      head: bytes.subarray(0, 4).toString('binary'),
    }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}
