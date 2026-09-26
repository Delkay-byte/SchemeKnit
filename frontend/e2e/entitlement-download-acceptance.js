/**
 * SchemeKnit entitlement + download live acceptance harness.
 *
 * Proves, against a REAL deployed environment, the two production blockers:
 *   1. A teacher can generate a plan, SEE it on the review screen, and download
 *      a real DOCX and a real PDF (bytes verified, not assumed).
 *   2. The FREE -> PRO entitlement is server-authoritative: only an admin can
 *      activate it, a teacher cannot self-upgrade, and revocation works.
 *
 * It drives the actual UI (not the API alone) so the browser download path is
 * exercised exactly as a teacher experiences it.
 *
 * Usage:
 *   TF_BASE_URL=https://schemeknit-frontend.onrender.com \
 *   TF_API_URL=https://schemeknit-api.onrender.com \
 *   TF_TEACHER_EMAIL=... TF_TEACHER_PASSWORD=... \
 *   TF_ADMIN_EMAIL=... TF_ADMIN_PASSWORD=... \
 *   TF_SCHEME_ID=... \
 *   node e2e/entitlement-download-acceptance.js [chrome|msedge]
 *
 * All env vars are echoed as CONFIGURED/NOT SET — never their values.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { record, summary } = require('./report')

process.on('unhandledRejection', (err) => {
  const msg = String((err && err.message) || err)
  if (/TargetClosedError|Target page, context or browser has been closed/.test(msg)) return
  console.error('Unhandled rejection:', msg)
  process.exitCode = 1
})

const CHANNEL = process.argv[2] || 'chrome'
const BASE = (process.env.TF_BASE_URL || 'http://localhost:3000').replace(/\/$/, '')
const API = (process.env.TF_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const SCHEME_ID = process.env.TF_SCHEME_ID || ''
const TEACHER = { email: process.env.TF_TEACHER_EMAIL || '', password: process.env.TF_TEACHER_PASSWORD || '' }
const ADMIN = { email: process.env.TF_ADMIN_EMAIL || '', password: process.env.TF_ADMIN_PASSWORD || '' }

const OUT = path.resolve(process.env.TF_DOWNLOAD_DIR || __dirname, 'entitlement-download-acceptance')

function configured(v) { return v ? 'CONFIGURED' : 'NOT SET' }

async function login(context, { email, password }) {
  const page = await context.newPage()
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[type="email"]', email)
  await page.fill('input[type="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 })
  return page
}

async function readPlan(page) {
  return page.evaluate(async (api) => {
    const token = sessionStorage.getItem('teachflow_token')
    const res = await fetch(`${api}/api/auth/my-plan`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) return { error: res.status }
    const j = await res.json()
    return {
      plan: j.plan || (j.edition === 'free' ? 'FREE' : 'PRO'),
      status: j.status,
      edition: j.edition,
      lesson_used: j.generations_used,
      lesson_limit: j.lesson_quota_limit ?? j.generation_limit,
      ai_used: j.ai_quota_used,
      ai_limit: j.ai_quota_limit ?? j.ai_credits,
      expires_at: j.expires_at,
    }
  }, API)
}

async function saveDownload(page, label, action, timeout = 60000) {
  const target = path.join(OUT, `${CHANNEL}-${label}`)
  try {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout }),
      action(),
    ])
    const suggested = download.suggestedFilename()
    await download.saveAs(target)
    const bytes = fs.readFileSync(target)
    return { ok: true, suggested, size: bytes.length, head: bytes.subarray(0, 5).toString('binary') }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

async function ensureExportPanel(page) {
  // The page loads an existing completed job on mount. If none exists, run the
  // documented generate flow (Preview Allocation -> Confirm & Generate).
  try {
    await page.waitForSelector('button:has-text("Download DOCX")', { timeout: 8000 })
    return 'existing'
  } catch { /* fall through to generate */ }

  const preview = page.locator('button:has-text("Preview Allocation")')
  if (!(await preview.count())) return 'unavailable'
  await preview.first().click()
  await page.waitForTimeout(1500)
  const gen = page.locator('button:has-text("Confirm & Generate")')
  if (!(await gen.count())) return 'unavailable'
  await gen.first().click()
  await page.waitForSelector('button:has-text("Download DOCX")', { timeout: 180000 })
  return 'generated'
}

/** Resolve the first generated lesson id for the scheme through the real API. */
async function resolveLessonId(page) {
  return page.evaluate(async ({ api, schemeId }) => {
    const token = sessionStorage.getItem('teachflow_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const status = await fetch(`${api}/api/generation/scheme/${schemeId}/status`, { headers })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
    if (!status || !status.id) return null
    const lessons = await fetch(`${api}/api/generation/${status.id}/lessons`, { headers })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
    const first = lessons && lessons.lesson_plans && lessons.lesson_plans[0]
    return (first && first.id) || null
  }, { api: API, schemeId: SCHEME_ID })
}

/**
 * Track the FINAL file request (GET /api/generation/downloads/{token}) for a
 * download click: status, content-type and whether the body is the real file.
 */
function watchFinalDownloads(page, sink) {
  page.on('response', async (r) => {
    if (!r.url().includes('/api/generation/downloads/')) return
    const ct = r.headers()['content-type'] || ''
    let head = ''
    try {
      const buf = await r.body()
      head = buf.subarray(0, 5).toString('binary')
    } catch (e) { head = `body-unreadable:${e.message}` }
    sink.push({ status: r.status(), contentType: ct, head })
  })
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })

  console.log('\n=== SchemeKnit entitlement + download acceptance ===')
  console.log(`  base=${BASE} api=${API} channel=${CHANNEL}`)
  console.log(`  teacher=${configured(TEACHER.email)} admin=${configured(ADMIN.email)} scheme=${configured(SCHEME_ID)}`)

  const missing = []
  if (!TEACHER.email || !TEACHER.password) missing.push('TF_TEACHER_EMAIL/PASSWORD')
  if (!SCHEME_ID) missing.push('TF_SCHEME_ID')
  if (missing.length) {
    record('required configuration present', false, `missing ${missing.join(', ')}`)
    summary('Entitlement + download acceptance')
    process.exit(1)
  }

  // 'bundled' (or omitted channel) uses Playwright's own Chromium: local
  // system Chrome has been observed to route navigations through a
  // download-manager hook that can hand back a non-backend 204.
  const launchOpts = { downloadsPath: OUT }
  if (CHANNEL && CHANNEL !== 'bundled' && CHANNEL !== 'chromium') {
    launchOpts.channel = CHANNEL
  }
  const browser = await chromium.launch(launchOpts)
  const teacherCtx = await browser.newContext({ acceptDownloads: true })
  const adminCtx = await browser.newContext({ acceptDownloads: true })

  try {
    // ── Teacher session ──────────────────────────────────────────────────
    let page = await login(teacherCtx, TEACHER)
    record('Teacher login', true, page.url())

    let plan = await readPlan(page)
    record('Teacher plan is readable (server-authoritative)', !plan.error,
      plan.error ? `HTTP ${plan.error}` : `${plan.plan} · ${plan.status}`)
    const startsFree = plan.plan === 'FREE'
    record('Teacher is FREE before admin activation', startsFree,
      startsFree ? 'FREE' : `already ${plan.plan} — admin transition cannot be measured`)

    // ── Generate + review visibility (PART B) ────────────────────────────
    await page.goto(`${BASE}/generate/${SCHEME_ID}/`, { waitUntil: 'domcontentloaded' })
    const how = await ensureExportPanel(page)
    record('Lesson generated / generation available', how !== 'unavailable', how)
    if (how === 'unavailable') throw new Error('No generation controls and no existing job')

    // The real review screen: the generated lesson detail page. It must show
    // the actual plan content (metadata, phases, assessment) — not a skeleton.
    const lessonId = await resolveLessonId(page)
    if (!lessonId) {
      record('Generated plan is visible on the review screen', false, 'no generated lesson found')
    } else {
      await page.goto(`${BASE}/lessons/${lessonId}/`, { waitUntil: 'domcontentloaded' })
      await page.waitForSelector('section[aria-label="Phase 2 Main Learning"]', { timeout: 30000 })
        .then(() => record('Lesson review page renders Phase 2 Main Learning', true, lessonId))
        .catch((e) => record('Lesson review page renders Phase 2 Main Learning', false, e.message))
      const body = await page.locator('body').innerText()
      const markers = ['Strand', 'Indicator', 'Assessment'].filter((m) => body.includes(m))
      const deep = /Phase 2|Main Learning/i.test(body) && /Objectives|Objective/i.test(body)
      record('Generated plan shows real curriculum sections',
        markers.length >= 2 && deep, `markers=[${markers.join(',')}] deep=${deep}`)
      const skeleton = /No lesson plans yet|not found/i.test(body)
      record('Review page is not an empty skeleton', !skeleton, '')
      await page.goto(`${BASE}/generate/${SCHEME_ID}/`, { waitUntil: 'domcontentloaded' })
      await page.waitForSelector('button:has-text("Download DOCX")', { timeout: 30000 })
    }

    // Refresh BEFORE downloading: the completed job (and export panel) must
    // survive a reload, proving the flow is not a one-shot in-memory state.
    await page.reload({ waitUntil: 'domcontentloaded' })
    const panelAfterReload = await page
      .waitForSelector('button:has-text("Download DOCX")', { timeout: 30000 })
      .then(() => true).catch(() => false)
    record('Export panel survives a page refresh', panelAfterReload,
      panelAfterReload ? 'Download DOCX present after reload' : 'panel gone after reload')

    // ── DOCX download (PART C) ───────────────────────────────────────────
    const dlPosts = []
    const finalHits = []
    const onResponse = (r) => {
      if (r.url().includes('/download-url')) {
        dlPosts.push({ status: r.status(), auth: !!r.request().headers()['authorization'] })
      }
    }
    page.on('response', onResponse)
    watchFinalDownloads(page, finalHits)

    const docx = await saveDownload(page, 'docx', () =>
      page.click('button:has-text("Download DOCX")'))
    const docxPost = dlPosts.find((p) => p.status === 200)
    record('DOCX request authenticated (Bearer on download-url POST)', !!docxPost && docxPost.auth,
      docxPost ? `HTTP ${docxPost.status}` : 'no download-url response seen')
    record('DOCX HTTP 200', !!docxPost && docxPost.status === 200,
      docxPost ? `HTTP ${docxPost.status}` : 'none')
    const docxFinal = finalHits[finalHits.length - 1]
    record('DOCX final file request succeeded', !!docxFinal && docxFinal.status === 200,
      docxFinal ? `HTTP ${docxFinal.status} ${docxFinal.contentType}` : 'no final GET seen')
    record('DOCX browser saved a file', docx.ok, docx.ok ? `${docx.suggested} (${docx.size} bytes)` : docx.error)
    if (docx.ok) {
      record('DOCX bytes valid (PK zip signature)', docx.head.startsWith('PK'), `head=${JSON.stringify(docx.head)}`)
      record('DOCX filename has .docx', docx.suggested.toLowerCase().endsWith('.docx'), docx.suggested)
    }

    // ── PDF download (PART C) ────────────────────────────────────────────
    const pdf = await saveDownload(page, 'pdf', () =>
      page.click('button:has-text("Download PDF")'), 180000)
    const pdfFinal = finalHits[finalHits.length - 1]
    record('PDF browser saved a file', pdf.ok, pdf.ok ? `${pdf.suggested} (${pdf.size} bytes)` : pdf.error)
    if (pdf.ok) {
      record('PDF final file request succeeded', !!pdfFinal && pdfFinal.status === 200,
        pdfFinal ? `HTTP ${pdfFinal.status} ${pdfFinal.contentType}` : 'no final GET seen')
      record('PDF bytes valid (%PDF signature)', pdf.head.startsWith('%PDF'), `head=${JSON.stringify(pdf.head)}`)
      record('PDF filename has .pdf', pdf.suggested.toLowerCase().endsWith('.pdf'), pdf.suggested)
    } else {
      // A missing converter is a documented environment limitation, not a
      // silent failure: the teacher must see the controlled message.
      await page.waitForTimeout(1000)
      const body = await page.locator('body').innerText()
      record('PDF failure surfaces a controlled message',
        /PDF (export|conversion)|converter/i.test(body), 'no controlled PDF message')
    }
    record('No "Failed to fetch" surfaced', !(await page.locator('body').innerText()).includes('Failed to fetch'), '')
    record('No generic "Action failed" surfaced', !(await page.locator('body').innerText()).includes('Action failed'), '')

    // ── Downloads in a NEW independently authenticated tab ───────────────
    // Tab-isolated auth: a fresh tab has its own sessionStorage, so this logs
    // in again and proves the download path works in another authenticated tab.
    try {
      const tab2 = await teacherCtx.newPage()
      await tab2.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' })
      await tab2.fill('input[type="email"]', TEACHER.email)
      await tab2.fill('input[type="password"]', TEACHER.password)
      await tab2.click('button[type="submit"]')
      await tab2.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 45000 })
      await tab2.goto(`${BASE}/generate/${SCHEME_ID}/`, { waitUntil: 'domcontentloaded' })
      await tab2.waitForSelector('button:has-text("Download DOCX")', { timeout: 30000 })
      const tab2Hits = []
      watchFinalDownloads(tab2, tab2Hits)
      const docx2 = await saveDownload(tab2, 'docx-tab2', () =>
        tab2.click('button:has-text("Download DOCX")'))
      record('DOCX downloads in a newly authenticated tab', docx2.ok && docx2.head.startsWith('PK'),
        docx2.ok ? `${docx2.suggested} (${docx2.size} bytes)` : docx2.error)
      await tab2.close()
    } catch (e) {
      record('DOCX downloads in a newly authenticated tab', false, e.message)
    }

    // ── Teacher cannot self-upgrade (PART A/I) ───────────────────────────
    const selfUpgrade = await page.evaluate(async (api) => {
      const token = sessionStorage.getItem('teachflow_token')
      const res = await fetch(`${api}/api/platform-admin/individual-teachers/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ teacher_id: 'self', product_plan_id: 'self', duration_days: 30 }),
      })
      return res.status
    }, API)
    record('Teacher self-upgrade is blocked (403)', selfUpgrade === 403, `HTTP ${selfUpgrade}`)

    const selfRevoke = await page.evaluate(async (api) => {
      const token = sessionStorage.getItem('teachflow_token')
      const res = await fetch(`${api}/api/platform-admin/individual-teachers/any/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ reason: 'self' }),
      })
      return res.status
    }, API)
    record('Teacher self-revoke is blocked (403)', selfRevoke === 403, `HTTP ${selfRevoke}`)

    // ── Admin activates PRO (PART G) ─────────────────────────────────────
    if (ADMIN.email && ADMIN.password && startsFree) {
      const adminPage = await login(adminCtx, ADMIN)
      record('Admin login', true, adminPage.url())
      await adminPage.goto(`${BASE}/platform-admin/`, { waitUntil: 'domcontentloaded' })
      await adminPage.click('button:has-text("teachers")').catch(() => {})
      await adminPage.waitForTimeout(1500)

      const row = adminPage.locator(`[data-teacher-row="${TEACHER.email}"]`)
      if (!(await row.count())) {
        record('Admin sees the teacher', false, `row not found for ${TEACHER.email}`)
      } else {
        record('Admin sees the teacher', true, '')
        const activateBtn = row.locator('[data-teacher-activate]')
        if (await activateBtn.count()) {
          const enabled = await activateBtn.first().isEnabled().catch(() => false)
          if (!enabled) {
            record('Admin activated PRO', false, 'activate button disabled (no plan selected?)')
          } else {
            await activateBtn.first().click()
            await adminPage.waitForTimeout(2500)
            record('Admin activated PRO', true, '')
          }
        } else {
          record('Admin activated PRO', false, 'activate button not offered (already PRO?)')
        }
      }

      // Teacher refreshes and now sees PRO.
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1500)
      const after = await readPlan(page)
      record('Teacher entitlement now PRO after refresh', after.plan === 'PRO' && after.status === 'active',
        `${after.plan} · ${after.status}`)

      // Revoke returns the teacher to FREE.
      if (await row.count() && await row.locator('[data-teacher-revoke]').count()) {
        await row.locator('[data-teacher-revoke]').first().click()
        await adminPage.waitForTimeout(1000)
        // Confirm INSIDE the dialog portal (a bare button selector would match
        // the row button behind the overlay and never confirm the revocation).
        const dlgConfirm = adminPage
          .locator('[role="dialog"]')
          .locator('button:has-text("Revoke")')
        if (await dlgConfirm.count()) {
          await dlgConfirm.last().click()
        } else {
          await adminPage.click('button:has-text("Revoke")').catch(() => {})
        }
        await adminPage.waitForTimeout(2500)
        await page.reload({ waitUntil: 'domcontentloaded' })
        await page.waitForTimeout(1500)
        const revoked = await readPlan(page)
        record('Revoking PRO returns teacher to FREE', revoked.plan === 'FREE',
          `${revoked.plan} · ${revoked.status}`)
      }
    } else if (!startsFree) {
      record('Admin activation transition', true, 'skipped — teacher already PRO')
    } else {
      record('Admin login/activation', false, 'TF_ADMIN_EMAIL/PASSWORD not configured')
    }
  } catch (e) {
    record('harness completed without throwing', false, e.message)
  } finally {
    try { await browser.close() } catch { /* already closed */ }
  }

  const ok = summary('Entitlement + download acceptance')
  fs.writeFileSync(path.join(OUT, 'results.txt'), `base=${BASE} api=${API}\n${
    require('./report').results.map((r) => `${r.pass ? 'PASS' : 'FAIL'} ${r.name}${r.detail ? ' — ' + r.detail : ''}`).join('\n')}\n`)
  process.exit(ok ? 0 : 1)
})()
