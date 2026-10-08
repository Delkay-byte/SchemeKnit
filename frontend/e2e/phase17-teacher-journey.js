/**
 * TeachFlow Phase 17 — end-to-end teacher acceptance journey (17E-17G).
 *
 * Drives a REAL browser through the full free-tier teacher flow against a
 * live backend + web app:
 *   - public signup (fresh Free Tier teacher per run)
 *   - PDF upload, multi-subject confirmation, review, approve
 *   - allocation preview with Free Tier pre-select/cap
 *   - generation (TF_RUN=A: ENHANCED via real Groq — partial allowance;
 *     TF_RUN=B: full AI credit burn 4->0, exhaustion 403, OFF after)
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
      const token = sessionStorage.getItem('teachflow_token') ||
                    localStorage.getItem('teachflow_token')
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
  // Priority 3: the week surface + quota line load themselves (no Preview
  // button). The quota text only exists once a FRESH preview has landed —
  // Start New Generation clears it, so this wait also sequences restarts.
  await page.waitForFunction(
    () => /Free Tier lesson plans used this month/.test(document.body.innerText),
    null,
    { timeout: 90000 },
  )
}

/** Click one per-lesson Generate/Regenerate (first enabled row) or the primary. */
async function clickGenerate(page, source = 'primary') {
  if (source === 'first-row') {
    const btns = page.locator('[data-week-row] [data-generate-lesson]')
    const n = await btns.count()
    for (let i = 0; i < n; i++) {
      if (await btns.nth(i).isEnabled()) {
        await btns.nth(i).click()
        return
      }
    }
    throw new Error('no enabled per-lesson Generate button')
  }
  await page.click('button:has-text("Generate lesson plans")')
}

async function waitForGenerate(page, wantN, timeoutMs = 300000) {
  const ok = await poll(() => genRespCount >= wantN, timeoutMs)
  if (!ok) throw new Error(`generate response #${wantN} not seen in ${timeoutMs}ms`)
  const settled = await page.waitForSelector('button:has-text("Start New Generation")', {
    timeout: timeoutMs,
  }).then(() => true).catch(() => false)
  return settled
}

async function generateAndWait(page, wantN, timeoutMs = 300000, source = 'primary') {
  await clickGenerate(page, source)
  return waitForGenerate(page, wantN, timeoutMs)
}

async function startNewGeneration(page) {
  await page.click('button:has-text("Start New Generation")')
  // Weeks clear, then the auto-preview rebuilds them.
  await page.waitForSelector('[data-allocation-weeks]', { state: 'detached', timeout: 15000 })
    .catch(() => {})
  await page.waitForSelector('[data-allocation-weeks]', { timeout: 30000 })
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
    await page.fill('input[placeholder="Re-enter your password"]', PASSWORD)
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
      'free-tier entitlement: 5 AI generations this month, none used',
      p0.ai_credits === 5 && p0.ai_quota_used === 0 && p0.edition === 'free',
      `edition=${p0.edition} ai_quota_used=${p0.ai_quota_used} remaining=${p0.ai_quota_remaining}`,
    )
    meta.ai_credits.push({ at: 'baseline', used: p0.ai_quota_used, remaining: p0.ai_quota_remaining })

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
      const ready = body.match(/(\d+) of (\d+) pending can be generated this month/)
      return {
        selectable: m ? Number(m[1]) : null,
        fit: ready ? Number(ready[1]) : null,
        pending: ready ? Number(ready[2]) : null,
      }
    })
    record(
      'full-set announces the allowance cap: "X of N pending can be generated this month" (X ≥ 5, N > 5)',
      selInfo.selectable > 5 && selInfo.fit !== null && selInfo.fit >= 5 &&
        selInfo.pending > selInfo.fit,
      JSON.stringify(selInfo),
    )

    if (RUN === 'A') {
      // ── A1: generate 1 unit, ENHANCED + real Groq content ──────────────
      genRespCount = genReqCount = 0
      await generateAndWait(page, 1, 300000, 'first-row')
      const r1 = respByN[1]
      const codes1 = (payloadByN[1] || {}).selected_indicator_codes || []
      record('teacher generates a single lesson occurrence (1 indicator in payload)',
        codes1.length === 1, JSON.stringify(codes1))
      meta.job_ids.push(r1 && r1.data && r1.data.job_id)
      record(
        'generation succeeds and consumes 1 lesson unit (0 of 5 -> 1 of 5)',
        r1 && r1.status === 200 && r1.data.quota && r1.data.quota.used === 1,
        r1 && r1.data && JSON.stringify(r1.data.quota),
      )
      meta.quota.push({ at: 'after-gen-1', ...(r1.data.quota || {}) })

      const jobId1 = r1.data.job_id
      const les1 = await api(page, 'GET', `/api/generation/${jobId1}/lessons`)
      const larr = ((les1.data || {}).lesson_plans) || []
      // Provider reality: Groq may answer OR rate-limit (429). Either way the
      // job succeeds — and the ledger must be honest: a lifetime/monthly AI
      // credit is consumed ONLY when provider content was actually produced.
      const consumed1 = r1 && r1.data ? r1.data.ai_credits_remaining !== null : false
      record(
        'AI honesty invariant: credit consumed iff provider content produced (provenance matches)',
        r1 && r1.status === 200 && larr.length > 0 &&
          larr.every((l) => l.ai_generated === consumed1) &&
          (!consumed1 || r1.data.ai_credits_remaining === 4),
        `remaining=${r1 && r1.data && r1.data.ai_credits_remaining} ` +
          `ai_generated=${JSON.stringify(larr.map((l) => l.ai_generated))} ` +
          `reason=${(r1.data.ai && r1.data.ai.reason) || ''}`,
      )
      const planA1 = await api(page, 'GET', '/api/auth/my-plan')
      record(
        'AI monthly ledger matches the first job exactly (1 consumed, else 0)',
        planA1.data &&
          planA1.data.ai_quota_used === (consumed1 ? 1 : 0) &&
          planA1.data.ai_quota_remaining === 5 - planA1.data.ai_quota_used,
        `ai_quota_used=${planA1.data && planA1.data.ai_quota_used} remaining=${planA1.data && planA1.data.ai_quota_remaining}`,
      )

      // ── A2: idempotent regeneration of the same indicator ───────────────
      await startNewGeneration(page)
      await previewAllocation(page)
      const uiQ2 = await quotaFromUi(page)
      genRespCount = genReqCount = 1
      await generateAndWait(page, 2, 300000, 'first-row')
      const r2 = respByN[2]
      const codes2 = (payloadByN[2] || {}).selected_indicator_codes || []
      const sameSet = JSON.stringify(codes1) === JSON.stringify(codes2)
      record('regeneration re-selects the same single indicator',
        codes2.length === 1 && sameSet, JSON.stringify(uiQ2))
      record(
        'idempotent regeneration: identical indicator set consumes ZERO extra units (used stays 1)',
        r2 && r2.status === 200 && r2.data.quota.used === 1 && sameSet,
        `used=${r2 && r2.data && r2.data.quota.used} same_codes=${sameSet} codes=${JSON.stringify(codes1)}`,
      )
      meta.quota.push({ at: 'after-regen', ...(r2.data.quota || {}) })
      meta.job_ids.push(r2.data.job_id)

      // ── A3: primary Generate fills the whole remaining allowance ────────
      await startNewGeneration(page)
      await previewAllocation(page)
      const readyA3 = await quotaFromUi(page)
      const fitA3 = await page.evaluate(() => {
        const m = document.body.innerText.match(/(\d+) of (\d+) pending can be generated this month/)
        return m ? { fit: Number(m[1]), pending: Number(m[2]) } : null
      })
      record('at 4 remaining, the full-set cap announces the fitting subset',
        !!readyA3 && readyA3.remaining === 4 && !!fitA3 && fitA3.fit >= 4,
        JSON.stringify({ ui: readyA3 && readyA3.raw, fitA3 }))
      genRespCount = genReqCount = 2
      await generateAndWait(page, 3)
      const r3 = respByN[3]
      const codes3 = (payloadByN[3] || {}).selected_indicator_codes || []
      record(
        'primary Generate spends the full remaining allowance: 4 NEW units (1 -> 5)',
        r3 && r3.status === 200 && r3.data.quota.used === 5 &&
          codes3.length === 4 && !codes3.includes(codes1[0]),
        `used=${r3 && r3.data && r3.data.quota.used} codes=${JSON.stringify(codes3)}`,
      )
      meta.quota.push({ at: 'exhausted', ...(r3.data.quota || {}) })
      meta.job_ids.push(r3.data.job_id)

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
      await page.locator('table tbody tr').first().locator('a:has-text("Open")').click()
      await page.waitForURL(/\/lessons\/[^/?#]+/, { timeout: 30000 })
      await page.waitForSelector('h1', { timeout: 30000 })
      const detail = await page.locator('body').innerText()
      record(
        'lesson detail renders week/lesson header + context + plan',
        /Week \d+/.test(detail) && /Lesson context/i.test(detail) &&
          /Lesson plan/i.test(detail) && !/Lesson not found/.test(detail),
        detail.match(/Week \d+ &bull; Lesson \d+|Week \d+ • Lesson \d+/)?.[0] || '',
      )

      // ── 17G: exhausted UI hard-caps ─────────────────────────────────────
      await page.goto(`${WEB}/generate/${meta.scheme_id}`, { waitUntil: 'domcontentloaded' })
      await waitForHydration(page)
      await page.waitForSelector('[data-allocation-weeks], button:has-text("Start New Generation")', { timeout: 60000 })
      if (await page.locator('button:has-text("Start New Generation")').count()) {
        await startNewGeneration(page)
      }
      await previewAllocation(page)
      const uiQEnd = await quotaFromUi(page)
      record('quota line at exhaustion: 5 of 5, 0 remaining',
        !!uiQEnd && uiQEnd.used === 5 && uiQEnd.remaining === 0, uiQEnd && uiQEnd.raw)
      meta.quota.push({ at: 'exhausted-ui', ...(uiQEnd || {}) })

      const dis = await page.evaluate(() => {
        const rowBtns = Array.from(document.querySelectorAll('[data-generate-lesson]'))
        const genBtn = Array.from(document.querySelectorAll('[data-generate-action] button'))
          .find((b) => /Generate lesson plans/.test(b.innerText))
        return {
          total: rowBtns.length,
          disabled: rowBtns.filter((b) => b.disabled).length,
          genDisabled: genBtn ? genBtn.disabled : null,
          hasReason: /used up/.test(document.body.innerText),
        }
      })
      record(
        'UI hard-caps at 0 remaining: every per-lesson Generate disabled, primary Generate disabled, reason stated',
        dis.total > 0 && dis.disabled === dis.total && dis.genDisabled === true && dis.hasReason,
        JSON.stringify(dis),
      )

      // ── 17G: server-side replay at 0 remaining blocked ──────────────────
      expect403 = true
      const replay = await api(page, 'POST', `/api/generation/${meta.scheme_id}/generate`, payloadByN[3])
      expect403 = false
      const detailMsg = replay.data && replay.data.detail
      record(
        'server rejects a replay at 0 remaining with 403 + teacher-facing quota message',
        replay.status === 403 && /You have 0 Free Tier lesson plans remaining/.test(String(detailMsg)),
        String(detailMsg).slice(0, 160),
      )

      const qEnd = await api(page, 'GET', '/api/generation/quota')
      record('final server quota: used 5, remaining 0 (atomic ledger intact)',
        qEnd.data && qEnd.data.used === 5 && qEnd.data.remaining === 0,
        JSON.stringify(qEnd.data))
      meta.quota.push({ at: 'final-api', ...(qEnd.data || {}) })

      const planEnd = await api(page, 'GET', '/api/auth/my-plan')
      record('Run A end-to-end: AI ledger advances only on successful provider batches (honest bounds)',
        planEnd.data &&
          planEnd.data.ai_quota_used >= (consumed1 ? 1 : 0) &&
          planEnd.data.ai_quota_used <= 3 &&
          planEnd.data.ai_quota_remaining === 5 - planEnd.data.ai_quota_used,
        `ai_quota_used=${planEnd.data && planEnd.data.ai_quota_used} remaining=${planEnd.data && planEnd.data.ai_quota_remaining}`)
      meta.ai_credits.push({ at: 'final', used: planEnd.data.ai_quota_used })
    } else {
      // ═══ RUN B: AI_MODE=groq pin — real AI credit lifecycle ═════════════
      genRespCount = genReqCount = 0
      await generateAndWait(page, 1, 300000, 'first-row')
      const r1 = respByN[1]
      const codesB1 = (payloadByN[1] || {}).selected_indicator_codes || []
      record('teacher generates a single lesson occurrence (1 indicator in payload)',
        codesB1.length === 1, JSON.stringify(codesB1))
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
          await generateAndWait(page, genRespCount + 1, 300000, 'first-row')
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
      const before6 = genRespCount
      expect403 = true
      await clickGenerate(page, 'first-row')
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
      record('AI ledger exactly 5/5 used after the blocked attempt',
        planEx.data && planEx.data.ai_quota_used === 5 && planEx.data.ai_quota_remaining === 0,
        `used=${planEx.data && planEx.data.ai_quota_used} remaining=${planEx.data && planEx.data.ai_quota_remaining}`)

      // B7: OFF still generates after AI exhaustion (fresh page state)
      await page.reload({ waitUntil: 'domcontentloaded' })
      await waitForHydration(page)
      await page.waitForSelector('[data-allocation-weeks], button:has-text("Start New Generation")', { timeout: 60000 })
      if (await page.locator('button:has-text("Start New Generation")').count()) {
        await startNewGeneration(page)
      }
      await previewAllocation(page)
      await page.locator('select:has(option[value="OFF"])').selectOption('OFF')
      await generateAndWait(page, genRespCount + 1, 300000, 'first-row')
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
      record('final AI ledger: 5 used, 0 remaining (monthly, honest)',
        planFin.data && planFin.data.ai_quota_used === 5 && planFin.data.ai_quota_remaining === 0,
        `used=${planFin.data && planFin.data.ai_quota_used} remaining=${planFin.data && planFin.data.ai_quota_remaining}`)
      meta.ai_credits.push({ at: 'final', used: planFin.data.ai_quota_used })

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
