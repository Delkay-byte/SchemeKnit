/**
 * TeachFlow Phase 17 — end-to-end teacher acceptance journey (17E-17G).
 *
 * Drives a REAL browser through the full free-tier teacher flow against a
 * live backend + web app:
 *   - public signup (fresh Free Tier teacher per run)
 *   - PDF upload, multi-subject confirmation, review, approve
 *   - allocation preview with Free Tier pre-select/cap
 *   - generation (TF_RUN=A: ENHANCED with broken Gemini -> deterministic
 *     survival; TF_RUN=B: AI_MODE=groq pin -> real Groq AI content)
 *   - lesson-quota consumption, idempotent regeneration, hard 6th-block 403
 *   - AI credit consumption (B), credits-exhausted 403, OFF-after-exhaustion
 *   - exports: DOCX / XLSX real bytes, PDF real-or-controlled, ZIP
 *     Pro-gated controlled message on Free Tier
 *   - lesson list + lesson detail rendering
 *
 * Usage:
 *   TF_RUN=A node e2e/phase17-teacher-journey.js chrome
 *   TF_RUN=B node e2e/phase17-teacher-journey.js chrome
 *
 * Env:
 *   TF_RUN      A (default) or B — different quota/AI assertions per run
 *   TF_WEB_URL  default http://localhost:3000
 *   TF_API_URL  default http://localhost:8000
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

const CHANNEL = process.argv[2] || 'chrome'
const RUN = (process.env.TF_RUN || 'A').toUpperCase()
const WEB = process.env.TF_WEB_URL || 'http://localhost:3000'
const API = process.env.TF_API_URL || 'http://localhost:8000'
const PDF = path.resolve(__dirname, '..', '..', 'backend', 'real_documents', 'BASIC 7 TERM 1.pdf')
const OUT = path.resolve(__dirname, '..', '..', 'backend', 'temp', 'ba', 'downloads')
const RESULT_JSON = path.resolve(__dirname, '..', '..', 'backend', 'temp', `phase17_e2e_${RUN}.json`)
const PASSWORD = 'Phase17!Accept1'
const EMAIL = `phase17${RUN.toLowerCase()}${Date.now()}@acceptance.test`
const NAME = `Phase 17 Teacher ${RUN}`

const meta = {
  run: RUN,
  channel: CHANNEL,
  email: EMAIL,
  scheme_id: null,
  job_ids: [],
  quota: [],
  ai_credits: [],
  payloads: [],
  paced_retries: 0,
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function poll(fn, timeout = 30000) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    if (await fn()) return true
    await sleep(150)
  }
  return false
}

// Next.js serves interactive HTML before React attaches its handlers. Clicking
// a submit button pre-hydration triggers a native form GET (inputs have no
// name attrs -> /signup/?) that silently does nothing. Wait for React first.
async function waitForHydration(page, timeout = 90000) {
  await page.waitForFunction(() => {
    const el = document.querySelector('button')
    if (!el) return false
    return Object.keys(el).some(
      (k) => k.startsWith('__reactFiber') || k.startsWith('__reactProps'),
    )
  }, null, { timeout })
}

async function saveDownload(page, label, action, timeout = 60000) {
  try {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout }),
      action(),
    ])
    const suggested = download.suggestedFilename()
    const dest = path.join(OUT, `${RUN}-${CHANNEL}-${label}-${suggested}`)
    await download.saveAs(dest)
    const bytes = fs.readFileSync(dest)
    return {
      ok: true, suggested, path: dest, size: bytes.length,
      head: bytes.subarray(0, 4).toString('binary'),
    }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

async function api(page, method, apiPath, body) {
  return page.evaluate(
    async ({ method, apiPath, body, API }) => {
      const token = localStorage.getItem('teachflow_token')
      const res = await fetch(API + apiPath, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      let data = null
      try { data = await res.json() } catch { /* no body */ }
      return { status: res.status, data }
    },
    { method, apiPath, body, API },
  )
}

function quotaFromUi(page) {
  return page.evaluate(() => {
    const m = document.body.innerText.match(
      /(\d+) of (\d+) Free Tier lesson plans used this month\s*·?\s*(\d+) remaining/,
    )
    return m
      ? { used: Number(m[1]), limit: Number(m[2]), remaining: Number(m[3]), raw: m[0] }
      : null
  })
}

async function previewAllocation(page) {
  await page.click('button:has-text("Preview Allocation")')
  await page.waitForFunction(
    () => /Free Tier lesson plans used this month/.test(document.body.innerText),
    null,
    { timeout: 90000 },
  )
}

async function selectCount(page, n) {
  for (let guard = 0; guard < 30; guard++) {
    const checked = page.locator('input[type=checkbox]:checked')
    const c = await checked.count()
    if (c <= n) break
    await checked.nth(c - 1).click()
  }
  return page.locator('input[type=checkbox]:checked').count()
}

async function generateAndWait(page, wantN, timeoutMs = 300000) {
  await page.click('button:has-text("Confirm & Generate")')
  const ok = await poll(() => genRespCount >= wantN, timeoutMs)
  if (!ok) throw new Error(`generate response #${wantN} not seen in ${timeoutMs}ms`)
  const settled = await page.waitForSelector('button:has-text("Start New Generation")', {
    timeout: timeoutMs,
  }).then(() => true).catch(() => false)
  return settled
}

async function startNewGeneration(page) {
  await page.click('button:has-text("Start New Generation")')
  await page.waitForSelector('button:has-text("Preview Allocation")', { timeout: 30000 })
}

// ── request/response capture (node side) ───────────────────────────────────
let lastGenPayload = null
let genReqCount = 0
let genRespCount = 0
const payloadByN = {}
const respByN = {}
let expect403 = false
let allowDownload403 = false
const badResponses = []
const pageErrors = []

function attachCapture(page) {
  page.on('request', (r) => {
    if (r.method() !== 'POST') return
    const url = r.url().split('?')[0]
    if (!/\/api\/generation\/[^/]+\/generate$/.test(url)) return
    genReqCount += 1
    try {
      lastGenPayload = r.postDataJSON()
      payloadByN[genReqCount] = lastGenPayload
      meta.payloads.push({
        n: genReqCount,
        selected: (lastGenPayload && lastGenPayload.selected_indicator_codes) || null,
        ai_mode: lastGenPayload && lastGenPayload.ai_mode,
      })
    } catch { /* not json */ }
  })
  page.on('response', (r) => {
    const url = r.url().split('?')[0]
    const status = r.status()
    if (status >= 400) {
      const isGen403 = expect403 && status === 403 && /\/api\/generation\/[^/]+\/generate$/.test(url)
      const isDl403 = allowDownload403 && status === 403 && /\/download-url$/.test(url)
      const isPdfWindow = /\/export\/pdf$|\/download-url$|\/downloads\//.test(url)
      if (!isGen403 && !isDl403 && !isPdfWindow) badResponses.push(`${status} ${url}`)
    }
    if (r.request().method() !== 'POST') return
    if (!/\/api\/generation\/[^/]+\/generate$/.test(url)) return
    genRespCount += 1
    const n = genRespCount
    r.json()
      .then((data) => { respByN[n] = { status, data } })
      .catch(() => { respByN[n] = { status } })
  })
  page.on('pageerror', (e) => pageErrors.push(e.message))
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  if (!fs.existsSync(PDF)) {
    console.error(`missing source PDF: ${PDF}`)
    process.exit(2)
  }
  const browser = await chromium.launch({ channel: CHANNEL, downloadsPath: OUT })
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage()
  attachCapture(page)

  console.log(`\n=== Phase 17 teacher journey — run ${RUN} / ${CHANNEL} ===`)

  try {
    // ── 17E: public signup -> dashboard ────────────────────────────────────
    await page.goto(`${WEB}/signup`, { waitUntil: 'domcontentloaded' })
    await waitForHydration(page)
    await page.fill('input[placeholder="Ama Mensah"]', NAME)
    await page.fill('input[placeholder="name@gmail.com"]', EMAIL)
    await page.fill('input[placeholder="Create a password"]', PASSWORD)
    await page.click('button:has-text("Create Account")')
    await page.waitForURL(/\/dashboard/, { timeout: 60000 })
    record('signup a new Free Tier teacher and land on the dashboard', true, EMAIL)

    const q0 = await api(page, 'GET', '/api/generation/quota')
    record(
      'free-tier lesson quota starts at 0 of 5 (server-authoritative)',
      q0.status === 200 && q0.data && q0.data.enforced === true &&
        q0.data.limit === 5 && q0.data.used === 0,
      JSON.stringify(q0.data),
    )
    meta.quota.push({ at: 'baseline', ...(q0.data || {}) })

    const plan0 = await api(page, 'GET', '/api/auth/my-plan')
    const p0 = plan0.data || {}
    record(
      'free-tier entitlement: 5 lifetime AI credits, none used',
      p0.ai_credits === 5 && p0.ai_credits_used === 0 && p0.edition === 'free',
      `edition=${p0.edition} ai_credits=${p0.ai_credits} used=${p0.ai_credits_used}`,
    )
    meta.ai_credits.push({ at: 'baseline', used: p0.ai_credits_used, remaining: p0.ai_credits - p0.ai_credits_used })

    // ── 17E: upload -> multi-subject confirm -> review -> approve ─────────
    await page.goto(`${WEB}/upload`, { waitUntil: 'domcontentloaded' })
    await waitForHydration(page)
    await page.setInputFiles('input[type="file"]', PDF)
    await page.click('button:has-text("Upload & Process")')
    await page.waitForSelector('text=Multiple subjects detected', { timeout: 180000 })
    record('PDF upload extracts a multi-subject document (confirmation gate)', true)

    await page.locator('button:has-text("Science")').first().click()
    await page.waitForURL(/\/review\/[^/]+\/?$/, { timeout: 60000 })
    const mScheme = page.url().match(/\/review\/([^/?#]+)/)
    meta.scheme_id = mScheme ? mScheme[1] : null
    record('teacher confirms the Science section before anything is generated', !!meta.scheme_id, meta.scheme_id)

    await page.waitForSelector('button:has-text("Approve & Configure")', { timeout: 60000 })
    await page.click('button:has-text("Approve & Configure")')
    await page.waitForURL(/\/generate\/[^/?#]+/, { timeout: 60000 })
    record('review -> Approve & Configure lands on the generate page', true, page.url())

    await page.locator('select:has(option[value="ENHANCED"])').selectOption('ENHANCED')
    record('AI Mode set to ENHANCED', true)

    // ── allocation preview: Free Tier pre-select cap ──────────────────────
    await previewAllocation(page)
    const uiQ1 = await quotaFromUi(page)
    record(
      'allocation preview shows the Free Tier quota line (0 of 5, 5 remaining)',
      !!uiQ1 && uiQ1.used === 0 && uiQ1.limit === 5 && uiQ1.remaining === 5,
      uiQ1 && uiQ1.raw,
    )
    meta.quota.push({ at: 'preview-1', ...(uiQ1 || {}) })

    const selInfo = await page.evaluate(() => {
      const body = document.body.innerText
      const m = body.match(/This scheme contains (\d+) instructional indicators?/)
      const checked = document.querySelectorAll('input[type=checkbox]:checked').length
      const all = document.querySelectorAll('input[type=checkbox]').length
      return { selectable: m ? Number(m[1]) : null, checked, all }
    })
    record(
      'free tier pre-selects exactly the remaining allowance (5 of N indicators)',
      selInfo.selectable > 5 && selInfo.checked === 5,
      JSON.stringify(selInfo),
    )

    if (RUN === 'A') {
      // ── A1: generate 1 unit, ENHANCED + broken Gemini -> deterministic ──
      const c1 = await selectCount(page, 1)
      record('teacher narrows selection to a single indicator', c1 === 1, `checked=${c1}`)
      genRespCount = genReqCount = 0
      await generateAndWait(page, 1)
      const r1 = respByN[1]
      const codes1 = (payloadByN[1] || {}).selected_indicator_codes || []
      meta.job_ids.push(r1 && r1.data && r1.data.job_id)
      record(
        'generation succeeds and consumes 1 lesson unit (0 of 5 -> 1 of 5)',
        r1 && r1.status === 200 && r1.data.quota && r1.data.quota.used === 1,
        r1 && r1.data && JSON.stringify(r1.data.quota),
      )
      meta.quota.push({ at: 'after-gen-1', ...(r1.data.quota || {}) })
      record(
        'survival path: broken Gemini falls back to deterministic — no AI credit consumed',
        r1 && r1.data && r1.data.ai_credits_remaining === null,
        `ai_credits_remaining=${r1 && r1.data && r1.data.ai_credits_remaining}`,
      )

      const jobId1 = r1.data.job_id
      const les1 = await api(page, 'GET', `/api/generation/${jobId1}/lessons`)
      const larr = ((les1.data || {}).lesson_plans) || []
      record(
        'job lessons marked ai_generated=false (deterministic, not fake-AI)',
        larr.length > 0 && larr.every((l) => l.ai_generated === false),
        `lessons=${larr.length} ai_generated=${JSON.stringify(larr.map((l) => l.ai_generated))}`,
      )
      const planA1 = await api(page, 'GET', '/api/auth/my-plan')
      record(
        'AI lifetime credits still untouched after failed-provider generation',
        planA1.data && planA1.data.ai_credits_used === 0,
        `ai_credits_used=${planA1.data && planA1.data.ai_credits_used}`,
      )

      // ── A2: idempotent regeneration of the same indicator ───────────────
      await startNewGeneration(page)
      await previewAllocation(page)
      const uiQ2 = await quotaFromUi(page)
      const c2 = await selectCount(page, 1)
      record('regeneration re-selects the same single indicator', c2 === 1, JSON.stringify(uiQ2))
      genRespCount = genReqCount = 1
      await generateAndWait(page, 2)
      const r2 = respByN[2]
      const codes2 = (payloadByN[2] || {}).selected_indicator_codes || []
      const sameSet = JSON.stringify(codes1) === JSON.stringify(codes2)
      record(
        'idempotent regeneration: identical indicator set consumes ZERO extra units (used stays 1)',
        r2 && r2.status === 200 && r2.data.quota.used === 1 && sameSet,
        `used=${r2 && r2.data && r2.data.quota.used} same_codes=${sameSet} codes=${JSON.stringify(codes1)}`,
      )
      meta.quota.push({ at: 'after-regen', ...(r2.data.quota || {}) })
      meta.job_ids.push(r2.data.job_id)

      // ── A3: fill with the first 4 indicators -> used 4 ──────────────────
      await startNewGeneration(page)
      await previewAllocation(page)
      const checkedA3 = await page.locator('input[type=checkbox]:checked').count()
      record('preview pre-selects first 4 remaining indicators', checkedA3 === 4, `checked=${checkedA3}`)
      genRespCount = genReqCount = 2
      await generateAndWait(page, 3)
      const r3 = respByN[3]
      record(
        'generating 4 indicators moves used 1 -> 4 (3 new units, 1 already counted)',
        r3 && r3.status === 200 && r3.data.quota.used === 4,
        `used=${r3 && r3.data && r3.data.quota.used}`,
      )
      meta.quota.push({ at: 'after-gen-4', ...(r3.data.quota || {}) })
      meta.job_ids.push(r3.data.job_id)

      // ── A4: 5th unit via a distinct previously-uncounted indicator ──────
      await startNewGeneration(page)
      await previewAllocation(page)
      const uiQ4 = await quotaFromUi(page)
      record(
        'at 1 remaining, preview pre-selects only that 1',
        !!uiQ4 && uiQ4.used === 4 && uiQ4.remaining === 1,
        uiQ4 && uiQ4.raw,
      )
      // swap the already-counted first code for the 5th distinct indicator
      const firstChecked = page.locator('input[type=checkbox]:checked')
      if ((await firstChecked.count()) > 0) await firstChecked.first().click()
      const boxes = page.locator('input[type=checkbox]')
      await boxes.nth(4).click()
      const c4 = await page.locator('input[type=checkbox]:checked').count()
      record('teacher swaps in a distinct 5th indicator', c4 === 1, `checked=${c4}`)
      genRespCount = genReqCount = 3
      await generateAndWait(page, 4)
      const r4 = respByN[4]
      const codes4 = (payloadByN[4] || {}).selected_indicator_codes || []
      record(
        '5th distinct unit accepted: used 5 of 5, remaining 0',
        r4 && r4.status === 200 && r4.data.quota.used === 5 && codes4[0] !== codes1[0],
        `used=${r4 && r4.data && r4.data.quota.used} fifth=${JSON.stringify(codes4)}`,
      )
      meta.quota.push({ at: 'exhausted', ...(r4.data.quota || {}) })
      meta.job_ids.push(r4.data.job_id)

      // ── 17H: exports from the final job (jobId active on this panel) ────
      const docx = await saveDownload(page, 'docx', () =>
        page.click('button:has-text("Download DOCX")'))
      record('[DOCX] download reaches disk and is a real DOCX',
        docx.ok && docx.head.startsWith('PK') && docx.suggested.toLowerCase().endsWith('.docx'),
        docx.ok ? `${docx.suggested} (${docx.size} bytes)` : docx.error)

      const xlsx = await saveDownload(page, 'xlsx', () =>
        page.click('button:has-text("Download Register (XLSX)")'), 60000)
      record('[XLSX] download reaches disk and is a real workbook (PK container)',
        xlsx.ok && xlsx.head.startsWith('PK') && xlsx.suggested.toLowerCase().endsWith('.xlsx'),
        xlsx.ok ? `${xlsx.suggested} (${xlsx.size} bytes)` : xlsx.error)

      const pdf = await saveDownload(page, 'pdf', () =>
        page.click('button:has-text("Download PDF")'), 120000)
      if (pdf.ok) {
        record('[PDF] download reaches disk and is a real PDF',
          pdf.head === '%PDF' && pdf.suggested.toLowerCase().endsWith('.pdf'),
          `${pdf.suggested} (${pdf.size} bytes)`)
      } else {
        await sleep(1500)
        const bodyText = await page.locator('body').innerText()
        const controlled = /PDF export requires a document converter|PDF conversion failed on the server/i.test(bodyText)
        record('[PDF] no download -> controlled, user-visible message', controlled,
          controlled ? 'controlled converter message shown' : `no download and no message (${pdf.error})`)
      }

      allowDownload403 = true
      const zip = await saveDownload(page, 'zip', () =>
        page.click('button:has-text("Export ZIP")'), 60000)
      allowDownload403 = false
      if (zip.ok) {
        record('[ZIP] download reaches disk and is a real archive',
          zip.head.startsWith('PK') && zip.suggested.toLowerCase().endsWith('.zip'),
          `${zip.suggested} (${zip.size} bytes)`)
      } else {
        await sleep(1500)
        const bodyText = await page.locator('body').innerText()
        const gated = /ZIP export is available with Teacher Pro/i.test(bodyText)
        record('[ZIP] Free Tier -> controlled Pro-gating message (not a crash)', gated,
          gated ? 'ZIP gated with Teacher Pro message' : `unexpected ZIP failure: ${zip.error}`)
      }

      // ── 17E: lesson list + detail ───────────────────────────────────────
      await page.goto(`${WEB}/lessons`, { waitUntil: 'domcontentloaded' })
      await waitForHydration(page)
      await page.waitForSelector('table tbody tr', { timeout: 60000 })
      const rowCount = await page.locator('table tbody tr').count()
      record('lessons list shows the generated lesson(s)', rowCount >= 1, `${rowCount} row(s)`)
      await page.locator('table tbody tr').first().locator('button:has-text("Open")').click()
      await page.waitForURL(/\/lessons\/[^/?#]+/, { timeout: 30000 })
      await page.waitForSelector('h1', { timeout: 30000 })
      const detail = await page.locator('body').innerText()
      record(
        'lesson detail renders week/lesson header + curriculum context + plan',
        /Week \d+/.test(detail) && /Curriculum Context/.test(detail) &&
          /Lesson Plan/.test(detail) && !/Lesson not found/.test(detail),
        detail.match(/Week \d+ &bull; Lesson \d+|Week \d+ • Lesson \d+/)?.[0] || '',
      )

      // ── 17G: exhausted UI hard-caps ─────────────────────────────────────
      await page.goto(`${WEB}/generate/${meta.scheme_id}`, { waitUntil: 'domcontentloaded' })
      await waitForHydration(page)
      await page.waitForSelector('button:has-text("Preview Allocation"), button:has-text("Start New Generation")', { timeout: 60000 })
      if (await page.locator('button:has-text("Start New Generation")').count()) {
        await startNewGeneration(page)
      }
      await page.waitForSelector('button:has-text("Preview Allocation")', { timeout: 30000 })
      await previewAllocation(page)
      const uiQEnd = await quotaFromUi(page)
      record('quota line at exhaustion: 5 of 5, 0 remaining',
        !!uiQEnd && uiQEnd.used === 5 && uiQEnd.remaining === 0, uiQEnd && uiQEnd.raw)
      meta.quota.push({ at: 'exhausted-ui', ...(uiQEnd || {}) })

      const dis = await page.evaluate(() => {
        const all = document.querySelectorAll('input[type=checkbox]')
        const disabled = document.querySelectorAll('input[type=checkbox]:disabled')
        const genBtn = Array.from(document.querySelectorAll('button'))
          .find((b) => /Confirm &\s*Generate/.test(b.innerText))
        return {
          total: all.length,
          disabled: disabled.length,
          genDisabled: genBtn ? genBtn.disabled : null,
        }
      })
      record(
        'UI hard-caps at 0 remaining: every indicator checkbox disabled, Generate disabled',
        dis.total > 0 && dis.disabled === dis.total && dis.genDisabled === true,
        JSON.stringify(dis),
      )

      // ── 17G: server-side 6th attempt blocked ────────────────────────────
      expect403 = true
      const replay = await api(page, 'POST', `/api/generation/${meta.scheme_id}/generate`, payloadByN[4])
      expect403 = false
      const detailMsg = replay.data && replay.data.detail
      record(
        'server rejects the 6th attempt with 403 + teacher-facing quota message',
        replay.status === 403 && /You have 0 Free Tier lesson plans remaining/.test(String(detailMsg)),
        String(detailMsg).slice(0, 160),
      )

      const qEnd = await api(page, 'GET', '/api/generation/quota')
      record('final server quota: used 5, remaining 0 (atomic ledger intact)',
        qEnd.data && qEnd.data.used === 5 && qEnd.data.remaining === 0,
        JSON.stringify(qEnd.data))
      meta.quota.push({ at: 'final-api', ...(qEnd.data || {}) })

      const planEnd = await api(page, 'GET', '/api/auth/my-plan')
      record('AI credits STILL unused end-to-end in run A (Gemini 401 never counted)',
        planEnd.data && planEnd.data.ai_credits_used === 0,
        `ai_credits_used=${planEnd.data && planEnd.data.ai_credits_used}`)
      meta.ai_credits.push({ at: 'final', used: planEnd.data.ai_credits_used })
    } else {
      // ═══ RUN B: AI_MODE=groq pin — real AI credit lifecycle ═════════════
      const c1 = await selectCount(page, 1)
      record('teacher narrows selection to a single indicator', c1 === 1, `checked=${c1}`)
      genRespCount = genReqCount = 0
      await generateAndWait(page, 1)
      const r1 = respByN[1]
      meta.job_ids.push(r1 && r1.data && r1.data.job_id)
      record(
        'live Groq generation through the real app: 1 lesson unit consumed',
        r1 && r1.status === 200 && r1.data.quota.used === 1,
        `used=${r1 && r1.data && r1.data.quota.used}`,
      )
      record(
        'AI lifetime credit consumed on success (5 -> 4)',
        r1 && r1.data && r1.data.ai_credits_remaining === 4,
        `ai_credits_remaining=${r1 && r1.data && r1.data.ai_credits_remaining}`,
      )
      meta.ai_credits.push({ at: 'gen-1', remaining: r1 && r1.data && r1.data.ai_credits_remaining })

      const jobId1 = r1.data.job_id
      const les1 = await api(page, 'GET', `/api/generation/${jobId1}/lessons`)
      const larr = ((les1.data || {}).lesson_plans) || []
      record(
        'job lessons marked ai_generated=true (real AI content, not fallback)',
        larr.length > 0 && larr.every((l) => l.ai_generated === true),
        `lessons=${larr.length} ai_generated=${JSON.stringify(larr.map((l) => l.ai_generated))}`,
      )

      // B2-B5: burn the remaining 4 credits via idempotent regenerations.
      // Groq's free tier allows ~3 requests per ~60s window (observed live:
      // 3 successes, then rate_limit -> deterministic fallback which burns NO
      // credit). If an ENHANCED attempt comes back without a credit consumed,
      // wait out the window and retry that same regeneration — the ledger
      // only moves on real successes.
      const seq = [r1.data.ai_credits_remaining]
      for (let i = 2; i <= 5; i++) {
        let ri = null
        for (let attempt = 1; attempt <= 3; attempt++) {
          await startNewGeneration(page)
          await previewAllocation(page)
          await selectCount(page, 1)
          await generateAndWait(page, genRespCount + 1)
          ri = respByN[genRespCount]
          const burned = ri && ri.data &&
            typeof ri.data.ai_credits_remaining === 'number'
          if (burned || attempt === 3) break
          meta.paced_retries += 1
          await sleep(70000)
        }
        seq.push(ri && ri.data && ri.data.ai_credits_remaining)
        if (!ri || !ri.data || ri.data.quota.used !== 1) {
          record(`AI regen #${i} keeps lesson units at 1 (already counted)`, false,
            `used=${ri && ri.data && ri.data.quota.used}`)
        }
        meta.ai_credits.push({ at: `gen-${i}`, remaining: ri && ri.data && ri.data.ai_credits_remaining })
        meta.job_ids.push(ri && ri.data && ri.data.job_id)
      }
      record(
        'AI credit burns 4->3->2->1->0 across successful regenerations',
        JSON.stringify(seq) === JSON.stringify([4, 3, 2, 1, 0]),
        `seq=${JSON.stringify(seq)} paced_retries=${meta.paced_retries}`,
      )

      // B6: 6th ENHANCED attempt -> 403 credits exhausted
      await startNewGeneration(page)
      await previewAllocation(page)
      await selectCount(page, 1)
      const before6 = genRespCount
      expect403 = true
      await page.click('button:has-text("Confirm & Generate")')
      const got6 = await poll(() => genRespCount > before6, 30000)
      const alertShown = await poll(async () => {
        const t = await page.locator('body').innerText()
        return /used all 5 free AI generations/i.test(t)
      }, 15000)
      const r6 = respByN[genRespCount]
      expect403 = false
      record(
        '6th ENHANCED attempt blocked: 403 + lifetime-allowance message, no job created',
        got6 && alertShown && r6 && r6.status === 403 &&
          /used all 5 free AI generations/i.test(String(r6.data && r6.data.detail)),
        r6 && String(r6.data && r6.data.detail || '').slice(0, 150),
      )
      const planEx = await api(page, 'GET', '/api/auth/my-plan')
      record('AI credits remain exactly 5/5 used after the blocked attempt',
        planEx.data && planEx.data.ai_credits_used === 5,
        `used=${planEx.data && planEx.data.ai_credits_used}`)

      // B7: OFF still generates after AI exhaustion (fresh page state)
      await page.reload({ waitUntil: 'domcontentloaded' })
      await waitForHydration(page)
      await page.waitForSelector('button:has-text("Preview Allocation"), button:has-text("Start New Generation")', { timeout: 60000 })
      if (await page.locator('button:has-text("Start New Generation")').count()) {
        await startNewGeneration(page)
      }
      await page.waitForSelector('button:has-text("Preview Allocation")', { timeout: 30000 })
      await previewAllocation(page)
      await selectCount(page, 1)
      await page.locator('select:has(option[value="OFF"])').selectOption('OFF')
      await generateAndWait(page, genRespCount + 1)
      const r7 = respByN[genRespCount]
      record(
        'AI exhaustion does NOT block deterministic OFF generation (200, credits untouched)',
        r7 && r7.status === 200 && r7.data.ai_credits_remaining === null &&
          r7.data.quota.used === 1,
        `used=${r7 && r7.data && r7.data.quota.used} ai_remaining=${r7 && r7.data && r7.data.ai_credits_remaining}`,
      )
      meta.quota.push({ at: 'after-off', ...(r7.data.quota || {}) })
      meta.job_ids.push(r7.data.job_id)

      const planFin = await api(page, 'GET', '/api/auth/my-plan')
      record('final AI ledger: 5 used, 0 remaining (lifetime, honest)',
        planFin.data && planFin.data.ai_credits_used === 5,
        `used=${planFin.data && planFin.data.ai_credits_used}`)
      meta.ai_credits.push({ at: 'final', used: planFin.data.ai_credits_used })

      // one DOCX export on the successful OFF job (panel is live here)
      const docx = await saveDownload(page, 'docx', () =>
        page.click('button:has-text("Download DOCX")'))
      record('[DOCX] run-B export reaches disk and is a real DOCX',
        docx.ok && docx.head.startsWith('PK') && docx.suggested.toLowerCase().endsWith('.docx'),
        docx.ok ? `${docx.suggested} (${docx.size} bytes)` : docx.error)
    }

    record('no uncaught page exceptions', pageErrors.length === 0,
      pageErrors.slice(0, 3).join(' | '))
    record('no unexpected failing requests', badResponses.length === 0,
      badResponses.slice(0, 6).join(' | '))
  } catch (e) {
    record('harness completed without throwing', false, e && e.message)
  } finally {
    try { await browser.close() } catch { /* already closed */ }
  }

  const ok = summary(`Phase 17 teacher journey (run ${RUN}, ${CHANNEL})`)
  try {
    fs.writeFileSync(RESULT_JSON, JSON.stringify({
      generated_at: new Date().toISOString(),
      ...meta,
      checks: results,
      passed: results.filter((r) => r.pass).length,
      failed: results.filter((r) => !r.pass).length,
    }, null, 2))
    console.log(`\nresults written -> ${RESULT_JSON}`)
  } catch (e) {
    console.error('failed to write results:', e.message)
  }
  process.exit(ok ? 0 : 1)
})()
