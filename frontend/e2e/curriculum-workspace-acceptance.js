/**
 * SchemeKnit curriculum-grounded workspace browser acceptance.
 *
 * Drives the REAL teacher journey end to end, as specified:
 *
 *   upload a scheme
 *     -> see what was extracted (per-week status, "Needs review")
 *     -> select a week
 *     -> review/adjust the period allocation
 *     -> generate
 *     -> the generated lesson is shown immediately in the workspace
 *     -> open "Source & alignment" (which part of my scheme produced this?)
 *     -> inspect Phase 1 / Main Learning / Assessment / Phase 3
 *     -> edit Main Learning, save, reload, confirm it persisted
 *     -> download DOCX and PDF (bytes verified, files opened)
 *     -> repeat the core path at a mobile viewport
 *
 * It also verifies the curriculum spine + provenance APIs the workspace reads.
 *
 * Usage:
 *   node e2e/curriculum-workspace-acceptance.js
 *
 * Env (all optional except credentials for a secured environment):
 *   TF_WEB_URL             frontend origin      (default http://localhost:3000)
 *   TF_API_URL             backend origin       (default http://localhost:8000)
 *   TF_TEACHER_EMAIL       teacher email        (default accept.teacher@schemeknit.test)
 *   TF_TEACHER_PASSWORD    teacher password     (default Accept#2026)
 *   TF_SCHEME_ID           use an existing scheme instead of uploading
 *   TF_UPLOAD_FILE         scheme to upload     (default ../../temp/accept-single-science.docx)
 *   TF_CHANNEL             playwright channel   (default: bundled chromium)
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { record, summary, results } = require('./report')

process.on('unhandledRejection', (err) => {
  const msg = String((err && err.message) || err)
  if (/TargetClosedError|Target page, context or browser has been closed/.test(msg)) return
  console.error('Unhandled rejection:', msg)
  process.exitCode = 1
})

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3000').replace(/\/$/, '')
const API = (process.env.TF_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const TEACHER = {
  email: process.env.TF_TEACHER_EMAIL || 'accept.teacher@schemeknit.test',
  password: process.env.TF_TEACHER_PASSWORD || 'Accept#2026',
}
const UPLOAD_FILE = process.env.TF_UPLOAD_FILE
  ? path.resolve(process.env.TF_UPLOAD_FILE)
  : path.resolve(__dirname, '../../temp/accept-single-science.docx')
const OUT = path.join(__dirname, 'curriculum-workspace-acceptance')
// PART 21: the journey types content a teacher could actually write. An
// internal/harness marker or an epoch stamp must never enter lesson content or
// an export, so this is a real classroom instruction with a short per-run
// suffix (base-36, never a 12-13 digit timestamp).
const MARKER = `Learners compare manual and automatic devices using classroom examples ${Date.now().toString(36)}`

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function configured(v) { return v ? 'CONFIGURED' : 'NOT SET' }

async function login(page) {
  await page.goto(`${WEB}/login/`, { waitUntil: 'domcontentloaded', timeout: 120000 })
  await page.fill('input[type="email"]', TEACHER.email)
  await page.fill('input[type="password"]', TEACHER.password)
  await page.click('button[type="submit"]')
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 90000 })
  return page
}

/**
 * A hosted instance can cold-start for longer than the journey timeouts (the
 * Render frontend spins down on idle), which surfaced as an opaque
 * "page.goto: Timeout" on the very first navigation. Warm it once, retrying,
 * so the measured checks are about the app rather than instance start-up.
 */
async function warmUp(browser) {
  const page = await browser.newPage()
  try {
    for (let attempt = 1; attempt <= 4; attempt++) {
      try {
        const res = await page.goto(`${WEB}/login/`, { waitUntil: 'domcontentloaded', timeout: 120000 })
        if (res && res.status() < 500) {
          await page.waitForSelector('input[type="email"]', { timeout: 120000 })
          return true
        }
      } catch (e) {
        console.log(`  warm-up attempt ${attempt} failed: ${e.message.split('\n')[0]}`)
      }
      await sleep(3000)
    }
    return false
  } finally {
    await page.close().catch(() => {})
  }
}

async function api(page, apiPath) {
  return page.evaluate(async ({ apiBase, p }) => {
    const token = sessionStorage.getItem('teachflow_token')
    const res = await fetch(`${apiBase}${p}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    let body = null
    try { body = await res.json() } catch { /* non-JSON */ }
    return { status: res.status, body }
  }, { apiBase: API, p: apiPath })
}

async function saveDownload(page, label, action, timeout = 90000) {
  const target = path.join(OUT, `${label}`)
  const hits = []
  // The POST that issues the one-time URL is the step that can fail before any
  // bytes move — record it so a missing download event still names its cause.
  const issues = []
  const onResponse = async (r) => {
    if (r.url().includes('/download-url')) {
      let body = ''
      try { body = (await r.text()).slice(0, 200) } catch { /* unreadable */ }
      issues.push({ status: r.status(), body })
      return
    }
    if (!r.url().includes('/api/generation/downloads/')) return
    const ct = r.headers()['content-type'] || ''
    let head = ''
    try { head = (await r.body()).subarray(0, 5).toString('binary') } catch { /* unreadable */ }
    hits.push({ status: r.status(), contentType: ct, head })
  }
  page.on('response', onResponse)
  // Console noise from the export path (api.ts logs network failures before
  // rethrowing) tells us whether the POST never left the page.
  const consoleMsgs = []
  const onConsole = (m) => {
    if (/download|export|network failure/i.test(m.text())) consoleMsgs.push(m.text().slice(0, 160))
  }
  page.on('console', onConsole)
  try {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout }),
      action(),
    ])
    const suggested = download.suggestedFilename()
    await download.saveAs(target)
    const bytes = fs.readFileSync(target)
    return {
      ok: true,
      suggested,
      size: bytes.length,
      bytes,
      head: bytes.subarray(0, 5).toString('binary'),
      mime: hits.length ? hits[hits.length - 1].contentType : '',
      http: hits.length ? hits[hits.length - 1].status : null,
      path: target,
    }
  } catch (e) {
    const issue = issues[issues.length - 1]
    const hit = hits[hits.length - 1]
    return {
      ok: false,
      error: e.message,
      mime: hit ? hit.contentType : '',
      detail: [
        issue ? `download-url HTTP ${issue.status} ${issue.body}` : 'no download-url response',
        hit ? `file GET ${hit.status}` : 'no file GET',
        `frame=${page.url().slice(0, 90)}`,
        consoleMsgs.length ? `console=${consoleMsgs.join(' ~ ')}` : null,
      ].filter(Boolean).join(' | '),
    }
  } finally {
    page.off('response', onResponse)
    page.off('console', onConsole)
  }
}

/** A DOCX "opens" when it is a real OOXML package with a document part. */
function docxOpens(bytes) {
  const text = bytes.toString('binary')
  return text.includes('[Content_Types].xml') && text.includes('word/document.xml')
}

/** A PDF "opens" when it has a header, a cross-reference/trailer and an EOF. */
function pdfOpens(bytes) {
  const head = bytes.subarray(0, 8).toString('binary')
  const tail = bytes.subarray(Math.max(0, bytes.length - 2048)).toString('binary')
  return head.startsWith('%PDF-') && /trailer|startxref/.test(tail) && tail.includes('%%EOF')
}

async function runDesktop(browser, state) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
  })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(e.message))
  // Any HTTP >= 400 seen in the journey — production throttling (429) and
  // auth/API regressions both show up here when a step later times out.
  const httpErrors = []
  page.on('response', (r) => {
    if (r.status() >= 400) {
      httpErrors.push(`${r.status()} ${r.url().startsWith(WEB) ? r.url().slice(WEB.length) : r.url()}`.slice(0, 140))
    }
  })
  // Log every scheme-status response body: the workspace restore hinges on
  // status === 'completed', and the failure mode was observed only in
  // production right after a download-triggered reload.
  page.on('response', (r) => {
    if (/\/api\/generation\/scheme\/[^/]+\/status/.test(r.url())) {
      r.text().then((t) => console.log('  [scheme-status]', r.status(), t.slice(0, 220))).catch(() => {})
    }
  })
  page.on('console', (m) => {
    if (m.type() === 'error') console.log('  [console.error]', m.text().replace(/\s+/g, ' ').slice(0, 220))
  })

  try {
    // ── 1. Login through the real form ─────────────────────────────────────
    await login(page)
    record('login through the UI', true, page.url())

    // ── 2. Scheme: upload the teacher's real scheme, or use an existing one ─
    let schemeId = process.env.TF_SCHEME_ID || ''
    if (!schemeId) {
      if (!fs.existsSync(UPLOAD_FILE)) {
        record('scheme available for the journey', false, `no file at ${UPLOAD_FILE}`)
        throw new Error('no scheme to process')
      }
      await page.goto(`${WEB}/upload`, { waitUntil: 'domcontentloaded' })
      await page.getByRole('heading', { name: /upload your scheme of work/i }).waitFor({ timeout: 30000 })
      await page.locator('input[type="file"]').setInputFiles(UPLOAD_FILE)
      await page.getByRole('button', { name: /upload & process/i }).click()
      // Either the process pauses on the confirmation card (a multi-subject
      // document, or a scheme whose class level the title omits) or the success
      // card reports the extracted curriculum directly.
      const reviewBtn = page.getByRole('button', { name: /review curriculum/i })
      const confirmCard = page.locator('[data-multi-subject]')
      await Promise.race([
        reviewBtn.waitFor({ timeout: 120000 }).catch(() => {}),
        confirmCard.waitFor({ timeout: 120000 }).catch(() => {}),
      ])

      // ── Defect 1: single-subject upload never says "multiple subjects" ────
      const uploadBody = await page.locator('body').innerText()
      const saysMultiple = /multiple subjects detected/i.test(uploadBody)
      record('single-subject upload never claims multiple subjects', !saysMultiple,
        saysMultiple ? 'SHOWED multiple subjects' : 'no false multi-subject message')

      if (await confirmCard.count()) {
        // The document names no class level (a real shape: the level lives only
        // in the curriculum codes, "B7.1.1.1.1"). The teacher confirms it —
        // curriculum authority, no guessing.
        const classSelect = page.locator('#confirm-class-level')
        if (await classSelect.count()) {
          // The options are fetched on mount — wait for them rather than
          // reading the select while it still shows only the placeholder.
          let classOptions = []
          for (let i = 0; i < 30; i += 1) {
            classOptions = await classSelect.locator('option').allInnerTexts()
            if (classOptions.some((o) => /^Basic 7$/.test(o.trim()))) break
            await page.waitForTimeout(500)
          }
          const wanted = process.env.TF_CLASS || 'Basic 7'
          const match = classOptions.find((o) => o.trim() === wanted)
            || classOptions.find((o) => new RegExp(wanted, 'i').test(o))
          if (match) {
            await classSelect.selectOption({ label: match })
            await page.waitForTimeout(250)
            record('teacher can confirm the class level the document omits', true, match.trim())
          } else {
            record('teacher can confirm the class level the document omits', false,
              `no option matching "${wanted}" in: ${classOptions.join(' | ')}`)
          }
        }
        // Confirm the single detected subject section.
        const subjectBtn = page.locator('[data-multi-subject] button').last()
        await subjectBtn.click()
        await page.waitForURL(/\/review\//, { timeout: 90000 })
      } else {
        record('upload parses and reports the extracted curriculum',
          /Curriculum extracted/i.test(uploadBody))
        const subjectCount = page.locator('[data-subject-count]')
        if (await subjectCount.count()) {
          record('upload reports the actual subject count',
            /1 subject detected/i.test(await subjectCount.first().innerText()),
            (await subjectCount.first().innerText()).trim())
        }
        await reviewBtn.click()
        await page.waitForURL(/\/review\//, { timeout: 60000 })
      }
      schemeId = page.url().split('/review/')[1].split(/[/?#]/)[0]
      record('upload a real scheme through the UI', true, `scheme=${schemeId}`)
    } else {
      record('scheme available for the journey', true, `using TF_SCHEME_ID=${schemeId}`)
    }
    state.schemeId = schemeId

    // ── 3. Curriculum spine API (what the workspace reads) ─────────────────
    const spine = await api(page, `/api/curriculum/${schemeId}/spine`)
    const spineOk = spine.status === 200 && Array.isArray(spine.body?.weeks)
    record('curriculum spine is readable', spineOk,
      spineOk ? `${spine.body.summary.total_weeks} weeks · v${String(spine.body.spine_version).slice(0, 8)}` : `HTTP ${spine.status}`)
    if (spineOk) {
      const weeks = spine.body.weeks
      const hasStatus = weeks.every((w) =>
        ['ok', 'needs_review', 'special', 'mixed'].includes(w.review_status))
      record('every week carries a teacher-facing review status', hasStatus,
        weeks.map((w) => `${w.week_number}:${w.review_status}`).join(' '))
      record('spine reports the source document', !!spine.body.source.filename, spine.body.source.filename)
      record('spine never uses the vague "Other" review state for a mixed week',
        weeks.every((w) => w.week_type !== 'other' || w.special_period_label),
        weeks.filter((w) => w.week_type === 'mixed').map((w) => `W${w.week_number}`).join(',') || 'no mixed weeks')
    }

    // ── 4. Extraction surface: the teacher sees what was read ──────────────
    await page.goto(`${WEB}/review/${schemeId}`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('[data-extraction-table]', { timeout: 30000 })
    record('extraction table is shown after processing', true)
    const rows = page.locator('[data-extraction-table] tbody tr')
    const rowCount = await rows.count()
    record('extraction table lists the extracted weeks', rowCount > 0, `${rowCount} rows`)
    const tableText = await page.locator('[data-extraction-table]').innerText()
    record('extraction status uses teacher-facing wording',
      /Parsed|Needs review|Revision|Assessment|SBA|Vacation/.test(tableText),
      tableText.includes('Needs review') ? 'includes a Needs review row' : 'all parsed')
    record('extraction table exposes no parser diagnostics',
      !/confidence|malformed|fallback path|score 0\./i.test(tableText))
    // Defect 4: the teacher-facing "Other" state is replaced by meaningful
    // classification (Teaching / Special period / Mixed week / Needs review).
    record('extraction table never labels a week "Other"',
      !/\bOther\b/.test(tableText),
      tableText.includes('Mixed week') ? 'Mixed week used' : 'no Other label')

    // Clicking a row selects that week and populates the week pane.
    const targetRow = rows.nth(Math.min(1, rowCount - 1))
    await targetRow.click()
    await page.waitForTimeout(600)
    const ariaSelected = await targetRow.getAttribute('aria-selected')
    record('clicking an extracted week selects it', ariaSelected === 'true', `aria-selected=${ariaSelected}`)

    // ── Defect 2: indicators the source HAS must be visible ────────────────
    const weekApi = await api(page, `/api/documents/${schemeId}/weeks`)
    const apiWeeks = weekApi.body?.weeks || []
    const weeksWithIndicators = apiWeeks.filter((w) => (w.indicators || []).length > 0)
    record('weeks whose source has an indicator keep it', weeksWithIndicators.length > 0,
      `${weeksWithIndicators.length}/${apiWeeks.length} weeks carry indicators`)
    record('extraction table renders real indicator codes',
      /[A-Za-z]?\d+\.\d+\.\d+\.\d+/.test(tableText),
      (tableText.match(/[A-Za-z]?\d+\.\d+\.\d+\.\d+/g) || []).slice(0, 2).join(','))

    // ── Defect 3: Needs review opens the actual problem ────────────────────
    const needsReviewRow = page.locator('[data-extraction-table] tbody tr[data-needs-review="true"]')
    const needsReviewCount = await needsReviewRow.count()
    if (needsReviewCount > 0) {
      await needsReviewRow.first().click()
      await page.waitForTimeout(600)
      const ctx = page.locator('[data-week-review-context]')
      const ctxVisible = (await ctx.count()) > 0 && (await ctx.first().isVisible())
      const ctxText = ctxVisible ? await ctx.first().innerText() : ''
      record('Needs review click opens the week review context', ctxVisible)
      record('review context names what needs attention',
        /indicator|strand|sub-strand|content standard/i.test(ctxText),
        ctxText.replace(/\s+/g, ' ').slice(0, 120))
      record('review context offers a way forward',
        /continue|not produce a lesson|nothing is guessed/i.test(await page.locator('body').innerText()))
    } else {
      record('Needs review click opens the week review context', true,
        'no needs-review weeks in this scheme')
    }

    // ── Defect 4/5: mixed week label + source date segments ───────────────
    const mixedWeek = apiWeeks.find((w) => w.week_type === 'mixed')
    if (mixedWeek) {
      record('mixed week is labelled "Mixed week", never "Other"',
        /Mixed week/i.test(tableText) && !/\|Other\|/.test(tableText),
        'extraction table shows Mixed week')
      await page.locator(`[data-extraction-table] tbody tr[data-week-row="${mixedWeek.week_number}"]`).click()
      await page.waitForTimeout(600)
      const segs = page.locator('[data-mixed-week-segments]')
      const segsVisible = (await segs.count()) > 0 && (await segs.first().isVisible())
      record('mixed week shows its special period and teaching segments', segsVisible)
      if (segsVisible) {
        const segText = await segs.first().innerText()
        record('midterm segment keeps the SOURCE date range',
          /\d{4}-\d{2}-\d{2}\s*→\s*\d{4}-\d{2}-\d{2}/.test(segText) && /MID-?TERM|SPECIAL/i.test(segText),
          segText.replace(/\s+/g, ' ').slice(0, 140))
        record('teaching segment is shown beside the special period',
          /Teaching:/i.test(segText))
      }
      const spineMixed = await api(page, `/api/curriculum/${schemeId}/spine`)
      const mixedSpine = (spineMixed.body?.weeks || []).find((w) => w.week_number === mixedWeek.week_number)
      record('spine exposes source-defined special segments',
        !!mixedSpine?.special_segments?.length && !!mixedSpine.special_segments[0].start,
        mixedSpine?.special_segments?.[0]?.start || 'none')
    } else {
      record('mixed week is labelled "Mixed week", never "Other"', true,
        'this scheme has no mixed week')
    }

    // ── 5. Allocation: review + adjust the period, then generate ───────────
    await page.goto(`${WEB}/generate/${schemeId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /preview allocation/i }).waitFor({ timeout: 30000 })
    record('generation mode defaults to Quick Generate',
      (await page.getByRole('radio', { name: /quick generate/i }).getAttribute('aria-checked')) === 'true')
    record('Build with me is offered as the secondary path',
      (await page.getByRole('radio', { name: /build with me/i }).count()) > 0)

    // Optional: select a specific export template (e.g. the Approved WAPEF
    // Plan) — TF_TEMPLATE is matched against the option labels.
    const wantTemplate = process.env.TF_TEMPLATE
    if (wantTemplate) {
      const sel = page.locator('#cfg-template')
      if (await sel.count()) {
        const opts = await sel.locator('option').allInnerTexts()
        const match = opts.find((o) => new RegExp(wantTemplate, 'i').test(o))
        if (match) {
          await sel.selectOption({ label: match })
          await page.waitForTimeout(300)
          record('selects the requested export template', true, match.trim())
          state.template = match.trim()
        } else {
          record('selects the requested export template', false,
            `no option matching "${wantTemplate}" in: ${opts.join(' | ')}`)
        }
      } else {
        record('selects the requested export template', false, '#cfg-template not found')
      }
    }

    // Capture the allocation preview the UI itself requests, so the check is on
    // the real payload the teacher's screen is built from.
    let preview = null
    const onPreview = async (r) => {
      if (!r.url().includes('/allocation-preview')) return
      try { preview = { status: r.status(), body: await r.json() } } catch { /* not json */ }
    }
    page.on('response', onPreview)
    await page.getByRole('button', { name: /preview allocation/i }).click()
    await page.waitForTimeout(2500)

    const periodInputs = page.locator('input[id^="period-"]')
    const periodCount = await periodInputs.count()
    record('allocation shows an editable teaching period per lesson', periodCount > 0,
      `${periodCount} editable slots`)

    // Provenance travels with the allocation row (no fabricated values).
    const provRow = preview?.body?.lesson_review?.find((r) => r.source_provenance)
    record('allocation rows carry source provenance',
      !!provRow && provRow.source_provenance.curriculum_source === 'Teacher scheme',
      provRow ? `week ${provRow.source_provenance.source_week} · ${provRow.source_provenance.indicator || 'no indicator'}` : `HTTP ${preview?.status ?? 'no response'}`)
    record('allocation rows expose a review state',
      !!preview?.body?.lesson_review?.every((r) => typeof r.needs_review === 'boolean'),
      'needs_review present on every row')
    // ── Defect 6/7/13: Quick Generate → Preview Allocation succeeds ────────
    record('Quick Generate → Preview Allocation succeeds', preview?.status === 200,
      `HTTP ${preview?.status ?? 'no response'}`)
    let quickPreviewBody = await page.locator('body').innerText()
    record('no "Validation failed" on the Quick Generate path',
      !/validation failed/i.test(quickPreviewBody))
    record('no "Action failed" on the Quick Generate path',
      !/action failed/i.test(quickPreviewBody))

    // ── Defect 6 root cause: clearing the term dates must NOT break it ─────
    const termStart = page.locator('#cfg-term-start')
    const termEnd = page.locator('#cfg-term-end')
    if (await termStart.count()) {
      await termStart.fill('')
      await termEnd.fill('')
      await page.waitForTimeout(200)
      let clearedPreview = null
      const onCleared = async (r) => {
        if (!r.url().includes('/allocation-preview')) return
        try { clearedPreview = { status: r.status(), body: await r.json() } } catch { /* not json */ }
      }
      page.on('response', onCleared)
      await page.getByRole('button', { name: /preview allocation/i }).click()
      await page.waitForTimeout(2500)
      page.off('response', onCleared)
      record('emptied term dates do not produce a validation failure',
        clearedPreview?.status === 200, `HTTP ${clearedPreview?.status ?? 'no response'}`)
      const clearedBody = await page.locator('body').innerText()
      record('emptied term dates never surface "Validation failed"',
        !/validation failed/i.test(clearedBody) && !/action failed/i.test(clearedBody),
        (clearedBody.match(/[^\n]*validation failed[^\n]*/i) || ['no validation-failed text'])[0].slice(0, 90))
    }

    // ── Defect 14: Build with me → Preview Allocation succeeds ────────────
    const buildRadio = page.getByRole('radio', { name: /build with me/i })
    if (await buildRadio.count()) {
      await buildRadio.click()
      await page.waitForTimeout(300)
      let buildPreview = null
      const onBuild = async (r) => {
        if (!r.url().includes('/allocation-preview')) return
        try { buildPreview = { status: r.status(), body: await r.json() } } catch { /* not json */ }
      }
      page.on('response', onBuild)
      await page.getByRole('button', { name: /preview allocation/i }).click()
      await page.waitForTimeout(2500)
      page.off('response', onBuild)
      record('Build with me → Preview Allocation succeeds', buildPreview?.status === 200,
        `HTTP ${buildPreview?.status ?? 'no response'}`)
      const buildBody = await page.locator('body').innerText()
      record('no "Validation failed" on the Build with me path',
        !/validation failed/i.test(buildBody))
      // Back to Quick Generate for the rest of the journey.
      await page.getByRole('radio', { name: /quick generate/i }).click()
      await page.waitForTimeout(300)
    }
    page.off('response', onPreview)

    if (periodCount > 0) {
      await periodInputs.first().fill('Monday · Period 1')
      await page.waitForTimeout(400)
      record('teacher can adjust the allocation period', true, 'set Monday · Period 1')
    }

    // Capture the generate request itself so a failure names its real cause
    // (HTTP status + the backend's teacher-facing detail) instead of only
    // timing out on the workspace selector.
    let generate = null
    const onGenerate = async (r) => {
      if (!/\/generate$/.test(new URL(r.url()).pathname)) return
      try { generate = { status: r.status(), body: await r.json() } } catch { /* not json */ }
    }
    page.on('response', onGenerate)
    await page.getByRole('button', { name: /confirm & generate/i }).first().click()
    try {
      await page.waitForSelector('[data-lesson-workspace]', { timeout: 300000 })
      record('generation completes and opens the workspace', true,
        generate ? `HTTP ${generate.status}` : '')
    } catch (e) {
      const banner = (await page.locator('body').innerText())
        .split('\n').map((s) => s.trim())
        .filter((s) => s && !/^(Home|Dashboard|Lesson Plans|Weekly Plan|Templates|Settings|Upload)$/.test(s))
        .slice(0, 6).join(' | ')
      record('generation completes and opens the workspace', false,
        `generate HTTP ${generate?.status ?? 'no response'} `
        + `${JSON.stringify(generate?.body || {}).slice(0, 160)} :: ${banner.slice(0, 160)}`)
      throw e
    } finally {
      page.off('response', onGenerate)
    }

    // ── 6. Workspace: the generated lesson is visible immediately ──────────
    await page.waitForSelector('[data-lesson-content]', { timeout: 60000 })
    const workspaceText = await page.locator('[data-lesson-content]').innerText()
    record('workspace shows the real lesson, not an empty editor',
      workspaceText.length > 200, `${workspaceText.length} chars`)
    for (const [label, re] of [
      ['Lesson topic', /lesson topic/i],
      ['Objectives', /objectives/i],
      ['Phase 1 · Starter', /phase 1/i],
      ['Phase 2 · Main Learning', /main learning/i],
      ['Assessment', /assessment/i],
      ['Phase 3 · Reflection', /phase 3|reflection/i],
    ]) {
      record(`workspace renders ${label}`, re.test(workspaceText))
    }
    const topicValue = await page.getByLabel('Lesson topic').first().inputValue()
    record('workspace lesson topic has real content', topicValue.trim().length > 0, topicValue.slice(0, 60))

    // ── 7. Source & alignment ("why this lesson?") ─────────────────────────
    const sa = page.locator('[data-source-alignment]')
    record('Source & alignment panel is present', (await sa.count()) > 0)
    await sa.locator('button').first().click()
    await page.waitForTimeout(400)
    const saText = await sa.innerText()
    record('Source & alignment names the scheme', /Scheme/i.test(saText), saText.replace(/\s+/g, ' ').slice(0, 140))
    record('Source & alignment names the source week', /Week \d+/i.test(saText))
    record('Source & alignment names the indicator',
      /Indicator/i.test(saText) && /[A-Za-z]?\d+\.\d+\.\d+\.\d+/.test(saText),
      (saText.match(/[A-Za-z]?\d+\.\d+\.\d+\.\d+/g) || []).slice(0, 2).join(','))
    record('Source & alignment states the generation path', /Curriculum-first/i.test(saText))

    // Provenance API agrees with the panel.
    const lessonIds = await api(page, `/api/generation/schemes/${schemeId}/lessons`)
    const firstLesson = lessonIds.body?.lesson_plans?.[0]
    record('generated lessons are retrievable', !!firstLesson, `count=${lessonIds.body?.lesson_plans?.length || 0}`)
    if (firstLesson) {
      state.lessonId = firstLesson.id
      const prov = await api(page, `/api/generation/lessons/${firstLesson.id}/provenance`)
      record('lesson provenance API answers "why this lesson?"',
        prov.status === 200 && !!prov.body?.source_week,
        prov.status === 200 ? `week ${prov.body.source_week} · ${prov.body.indicator || 'no indicator'} · ${prov.body.generation}` : `HTTP ${prov.status}`)
      record('lesson provenance never fabricates a missing source',
        typeof prov.body?.scheme === 'string')
      state.sourceWeek = firstLesson.week_number
      state.teachingWeek = firstLesson.teaching_week || firstLesson.week_number
    }

    // ── 8. Edit Main Learning, save, reload, confirm persistence ───────────
    const act1 = page.getByLabel('Main learning activity 1')
    const editable = (await act1.count()) > 0 && (await act1.first().isEditable().catch(() => false))
    record('Main Learning is editable in the workspace', editable)
    if (editable) {
      await act1.first().fill(MARKER)
      await page.waitForTimeout(200)
      record('unsaved edits are signalled', /Unsaved changes/i.test(await page.locator('[data-lesson-workspace]').innerText()))
      await page.getByRole('button', { name: /^save$/i }).first().click()
      await page.waitForTimeout(3000)
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.waitForSelector('[data-lesson-content]', { timeout: 60000 })
      const afterReload = await page.getByLabel('Main learning activity 1').first().inputValue()
      record('edited Main Learning persists after save + reload', afterReload === MARKER,
        JSON.stringify(afterReload).slice(0, 70))
    }

    // ── 9. Export: DOCX + PDF from the workspace ──────────────────────────
    // Each export starts from a fresh page load. Chrome suppresses a second
    // automatic download triggered from the same page session, so the export
    // that follows another one never produced a download event even though the
    // server served the file (verified independently). Reloading clears that
    // per-page state without changing what the teacher clicks.
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.waitForSelector('[data-lesson-workspace]', { timeout: 120000 })
    await page.waitForSelector('[data-lesson-content]', { timeout: 60000 })
    const docx = await saveDownload(page, 'workspace.docx', () =>
      page.getByRole('button', { name: /export docx/i }).first().click(), 240000)
    record('DOCX download reaches disk', docx.ok,
      docx.ok ? `${docx.suggested} (${docx.size} bytes)` : `${docx.error} :: ${docx.detail}`)
    if (docx.ok) {
      record('DOCX HTTP 200', docx.http === 200, `HTTP ${docx.http}`)
      record('DOCX is a real zip package (PK signature)', docx.head.startsWith('PK'), JSON.stringify(docx.head))
      record('DOCX MIME is an OOXML document', /officedocument|octet-stream|zip/i.test(docx.mime), docx.mime)
      record('DOCX filename ends in .docx', /\.docx$/i.test(docx.suggested), docx.suggested)
      record('DOCX opens as an OOXML package', docxOpens(docx.bytes))
      state.docxOk = true
    }

    // The PDF export uses its own fresh page load for the same reason.
    console.log('  pdf step: reloading from', page.url())
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.waitForSelector('[data-lesson-workspace]', { timeout: 120000 })
    await page.waitForSelector('[data-lesson-content]', { timeout: 60000 })
    const pdf = await saveDownload(page, 'workspace.pdf', () =>
      page.getByRole('button', { name: /export pdf/i }).first().click(), 240000)
    record('PDF download reaches disk', pdf.ok,
      pdf.ok ? `${pdf.suggested} (${pdf.size} bytes)` : `${pdf.error} :: ${pdf.detail}`)
    if (pdf.ok) {
      record('PDF HTTP 200', pdf.http === 200, `HTTP ${pdf.http}`)
      record('PDF has the %PDF signature', pdf.head.startsWith('%PDF-'), JSON.stringify(pdf.head))
      record('PDF MIME is application/pdf', /application\/pdf/i.test(pdf.mime), pdf.mime)
      record('PDF filename ends in .pdf', /\.pdf$/i.test(pdf.suggested), pdf.suggested)
      record('PDF opens (header + xref + EOF)', pdfOpens(pdf.bytes))
      state.pdfOk = true
    } else {
      const body = await page.locator('body').innerText()
      record('PDF failure surfaces a controlled message',
        /PDF (export|conversion)|converter/i.test(body) && !/Failed to fetch/i.test(body))
    }

    const finalBody = await page.locator('body').innerText()
    record('no "Failed to fetch" surfaced', !finalBody.includes('Failed to fetch'))
    record('no generic "Action failed" surfaced', !finalBody.includes('Action failed'))
    record('no uncaught page exceptions (desktop)', pageErrors.length === 0,
      pageErrors.slice(0, 3).join(' | '))

    await page.screenshot({ path: path.join(OUT, 'workspace-1440.png'), fullPage: false })
  } catch (e) {
    // Forensics: what the teacher would actually see at the failure point.
    const forensics = await page.evaluate(() => ({
      readyState: document.readyState,
      text: (document.body && document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 300),
      pending: performance.getEntriesByType('resource')
        .filter(r => !r.responseEnd)
        .map(r => r.name.split('/').slice(-2).join('/')).slice(0, 8),
      last: performance.getEntriesByType('resource')
        .sort((a, b) => b.responseEnd - a.responseEnd).slice(0, 6)
        .map(r => `${Math.round(r.duration)}ms ${r.name.split('/').slice(-2).join('/')}`),
    })).catch(() => ({}))
    await page.screenshot({ path: path.join(OUT, 'desktop-failure.png') }).catch(() => {})
    record('desktop journey completed without throwing', false,
      `${e.message} :: url=${page.url().replace(WEB, '')} :: state=${forensics.readyState}` +
      ` :: text=${JSON.stringify(forensics.text || '')}` +
      ` :: pending=${JSON.stringify(forensics.pending || [])}` +
      ` :: last=${JSON.stringify(forensics.last || [])}` +
      ` :: pageErrors=${JSON.stringify(pageErrors.slice(-3))}` +
      ` :: recentHTTP=${httpErrors.slice(-10).join(' | ') || 'none'}`)
  } finally {
    await context.close().catch(() => {})
  }
}

async function runMobile(browser, state) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    acceptDownloads: true,
  })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(e.message))
  try {
    await login(page)
    record('mobile: login works', true)

    if (!state.schemeId) throw new Error('no scheme from the desktop journey')

    // Extraction table stays usable (scrolls, never overflows the page).
    await page.goto(`${WEB}/review/${state.schemeId}`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('[data-extraction-table]', { timeout: 30000 })
    const reviewOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    record('mobile: no horizontal page overflow on extraction', reviewOverflow <= 2, `overflow=${reviewOverflow}px`)

    // Workspace: lesson content primary, Save + Export reachable.
    await page.goto(`${WEB}/generate/${state.schemeId}`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('[data-lesson-workspace]', { timeout: 120000 })
    await page.waitForSelector('[data-lesson-content]', { timeout: 60000 })
    record('mobile: generated lesson is visible in the workspace', true)
    record('mobile: Save is reachable',
      await page.getByRole('button', { name: /^save$/i }).first().isVisible())
    record('mobile: Export DOCX is reachable',
      await page.getByRole('button', { name: /export docx/i }).first().isVisible())
    const wsOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    record('mobile: no horizontal page overflow in the workspace', wsOverflow <= 2, `overflow=${wsOverflow}px`)
    record('mobile: Source & alignment collapses by default',
      (await page.locator('[data-source-alignment] button').first().getAttribute('aria-expanded')) === 'false')
    await page.screenshot({ path: path.join(OUT, 'workspace-390.png'), fullPage: false })
    record('no uncaught page exceptions (mobile)', pageErrors.length === 0,
      pageErrors.slice(0, 3).join(' | '))
  } catch (e) {
    record('mobile journey completed without throwing', false, e.message)
  } finally {
    await context.close().catch(() => {})
  }
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  console.log('\n=== SchemeKnit curriculum-grounded workspace acceptance ===')
  console.log(`  web=${WEB} api=${API}`)
  console.log(`  teacher=${configured(TEACHER.email)} scheme=${configured(process.env.TF_SCHEME_ID)} upload=${fs.existsSync(UPLOAD_FILE) ? 'FOUND' : 'NOT FOUND'}`)

  const launchOpts = { downloadsPath: OUT }
  const channel = process.env.TF_CHANNEL
  if (channel && channel !== 'bundled' && channel !== 'chromium') launchOpts.channel = channel
  const browser = await chromium.launch(launchOpts)
  const state = {}
  try {
    const warm = await warmUp(browser)
    console.log(`  warm-up=${warm ? 'READY' : 'SLOW (continuing)'}`)
    await runDesktop(browser, state)
    await runMobile(browser, state)
  } finally {
    await browser.close().catch(() => {})
  }

  const ok = summary('Curriculum-grounded workspace acceptance')
  fs.writeFileSync(path.join(OUT, 'results.txt'),
    `web=${WEB} api=${API} scheme=${state.schemeId || ''}\n` +
    results.map((r) => `${r.pass ? 'PASS' : 'FAIL'} ${r.name}${r.detail ? ' — ' + r.detail : ''}`).join('\n') + '\n')
  process.exit(ok ? 0 : 1)
})()
