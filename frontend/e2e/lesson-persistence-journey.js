/**
 * SchemeKnit lesson-persistence browser journey (PHASE 9/10/11).
 *
 * The journey the previous report did NOT execute — on the real app, against
 * the real backend:
 *
 *   sign up a teacher
 *     -> set the SCHOOL in Settings (PART 7)
 *     -> upload the real BS7 code-only Computing scheme
 *     -> confirm the class the document omits
 *     -> approve extraction -> generate page
 *     -> select the Approved WAPEF Plan (PART 10)
 *     -> preview the allocation and set the four WAPEF fields, with MORE THAN
 *        ONE Through line (PART 8)
 *     -> generate
 *     -> the workspace shows the WAPEF lesson
 *     -> edit school-independent fields: topic, starter, main learning,
 *        assessment, phase 3, Class Assignment, Home Assignment, keywords,
 *        lesson resources, references, Deep Hope, Storyline, Through lines,
 *        God's Story
 *     -> Save
 *     -> leave for the dashboard, return to the lesson, RELOAD
 *     -> every edited value is still exactly what was saved (PART 9/36)
 *     -> the /lessons/{id} surface shows the same values
 *     -> export DOCX and PDF; both carry the lesson (PART 10)
 *
 * Usage:
 *   node e2e/lesson-persistence-journey.js
 * Requires: backend on :8000 and the production frontend (`next start`) on :3000.
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
const OUT = path.join(__dirname, 'lesson-persistence-journey')
fs.mkdirSync(OUT, { recursive: true })

const STAMP = Date.now()
const EMAIL = `persist.teacher.${STAMP}@schemeknit.test`
const PASSWORD = 'Persist#2026'
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
 * silently wiped when the app swaps in the hydrated tree (a cold Render
 * deploy hydrates seconds after domcontentloaded; localhost is instant).
 * A one-shot probe is not enough — hydration can replace the DOM after the
 * probe sticks — so the value must SURVIVE a settle window.
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
  await page.locator('#signup-name').fill('Persistence Teacher')
  await page.locator('#signup-email').fill(EMAIL)
  await page.locator('#signup-password').fill(PASSWORD)
  await page.locator('#signup-confirm').fill(PASSWORD)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 60000 })
}

/** PART 7 — the school is stored on the teacher profile, once. */
async function setSchoolInSettings(page) {
  await page.goto(`${WEB}/settings`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  const input = page.locator('#profile-school')
  await input.waitFor({ timeout: 30000 })
  await waitHydrated(page, '#profile-school')
  await input.fill(SCHOOL)
  await page.getByRole('button', { name: /save profile/i }).click()
  await page.waitForTimeout(1500)
  const shown = await input.inputValue().catch(() => '')
  return shown
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

  await page.locator('#cfg-term-start').fill('2026-09-14')
  await page.locator('#cfg-term-end').fill('2026-09-25')
  await page.locator('#cfg-lessons-per-week').fill(perWeek)
  // Priority 3: the week surface refreshes itself after config changes.
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
  // Record WHICH rows production numbered — the draft↔lesson alignment marker.
  const rowIds = await page.locator('select[id^="wapef-deep-hope-"]')
    .evaluateAll((els) => els.map((e) => e.id)).catch(() => [])
  console.log(`[diag] preview WAPEF row ids: ${rowIds.join(', ') || 'NONE'}`)
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
  await page.getByRole('button', { name: /generate lesson plans/i }).click()
  await page.locator('[data-lesson-workspace]').waitFor({ timeout: 180000 })
  await page.waitForTimeout(1500)
}

/**
 * The workspace is the ONLY surface whose fields are the lesson's. The
 * generate page keeps its own allocation-preview rows on screen (each with
 * its own WAPEF controls), so every read and write is scoped to
 * [data-lesson-workspace] — otherwise the journey would edit a preview row and
 * verify a different element than the one it changed.
 */
function workspace(page) {
  return page.locator('[data-lesson-workspace]').first()
}

/** Fill every teacher-owned field in the workspace and return what was typed. */
async function editEverything(page, picks) {
  const ws = workspace(page)
  const typed = {}
  const setText = async (label, value) => {
    const loc = ws.getByLabel(label, { exact: true }).first()
    await loc.waitFor({ timeout: 30000 })
    await loc.fill(value)
    typed[label] = value
  }

  typed.lessonTopic = picks.topic
  await ws.getByLabel('Lesson topic', { exact: true }).fill(picks.topic)
  await setText('Phase 1 starter', picks.starter)
  await setText('Main learning activity 1', picks.main)
  await setText('Assessment', picks.assessment)
  await setText('Phase 3 reflection', picks.conclusion)
  await setText('Class assignment', picks.classAssignment)
  await setText('Home assignment', picks.homeAssignment)

  // Keywords — a lesson generated without keywords must still accept one, so
  // the journey ADDS the first entry when the list is empty, then edits it.
  if (!(await ws.getByLabel('Keyword 1', { exact: true }).count())) {
    await ws.getByRole('button', { name: /add keyword/i }).click()
  }
  const kw = ws.getByLabel('Keyword 1', { exact: true }).first()
  await kw.fill(picks.keyword)
  typed.keyword = picks.keyword

  // Lesson resources — the LESSON's own list (PART 13/26).
  if (!(await ws.getByLabel('Lesson resource 1', { exact: true }).count())) {
    await ws.getByRole('button', { name: /add resource/i }).click()
  }
  const res = ws.getByLabel('Lesson resource 1', { exact: true }).first()
  await res.fill(picks.resource)
  typed.resource = picks.resource

  // References — add one if the lesson has none, then retitle it and pin its
  // type to this subject's curriculum.
  if (!(await ws.getByLabel('Reference 1 title', { exact: true }).count())) {
    await ws.getByRole('button', { name: /add reference/i }).click()
  }
  const refTitle = ws.getByLabel('Reference 1 title', { exact: true }).first()
  await refTitle.fill(picks.referenceTitle)
  typed.referenceTitle = picks.referenceTitle
  const refType = ws.getByLabel('Reference 1 type', { exact: true }).first()
  const labels = await refType.locator('option').allInnerTexts()
  const subjectOption = labels.find((l) => /Curriculum/i.test(l))
  if (subjectOption) {
    await refType.selectOption({ label: subjectOption })
    typed.referenceType = subjectOption
  }

  // The four WAPEF fields (PART 8/22) — in the WORKSPACE, not a preview row.
  await ws.getByLabel('Deep Hope', { exact: true }).selectOption({ label: picks.deepHope })
  await ws.getByLabel('Storyline', { exact: true }).selectOption({ label: picks.storyline })
  await ws.getByLabel("God's Story", { exact: true }).selectOption({ label: picks.godsStory })
  // Through lines are toggle chips: the config step may already have selected
  // the first two, so only click the ones that are NOT pressed (clicking a
  // selected chip would deselect it and store an empty list).
  const throughButtons = ws.locator('button[aria-pressed]')
  const count = await throughButtons.count()
  const chosen = []
  for (let i = 0; i < count && chosen.length < 2; i += 1) {
    const chip = throughButtons.nth(i)
    const pressed = (await chip.getAttribute('aria-pressed')) === 'true'
    if (!pressed) await chip.click()
    chosen.push((await chip.innerText()).trim())
  }
  typed.throughLines = chosen
  return typed
}

async function save(page) {
  await page.getByRole('button', { name: /^Save$/ }).first().click()
  const banner = page.getByText(/your edits are stored with this lesson/i)
  await banner.waitFor({ timeout: 60000 }).catch(() => {})
  const saved = await banner.isVisible().catch(() => false)
  const body = await page.locator('body').innerText()
  return { saved, actionFailed: /Action failed|Internal server error/i.test(body) }
}

/** Read the workspace inputs back (what the teacher actually sees). */
async function readWorkspace(page) {
  const ws = workspace(page)
  const read = async (label) => {
    const loc = ws.getByLabel(label, { exact: true }).first()
    if (!(await loc.count())) return null
    return loc.inputValue().catch(() => null)
  }
  const selectLabel = async (label) => {
    const loc = ws.getByLabel(label, { exact: true }).first()
    if (!(await loc.count())) return null
    return loc.inputValue().catch(() => null)
  }
  const through = []
  const buttons = ws.locator('button[aria-pressed]')
  const n = await buttons.count()
  for (let i = 0; i < n; i += 1) {
    if ((await buttons.nth(i).getAttribute('aria-pressed')) === 'true') {
      through.push((await buttons.nth(i).innerText()).trim())
    }
  }
  const deepSel = ws.locator('select[aria-label="Deep Hope"]')
  const deepCount = await deepSel.count()
  return {
    _diag: { deepSelects: deepCount },
    lessonTopic: await read('Lesson topic'),
    starter: await read('Phase 1 starter'),
    main: await read('Main learning activity 1'),
    assessment: await read('Assessment'),
    conclusion: await read('Phase 3 reflection'),
    classAssignment: await read('Class assignment'),
    homeAssignment: await read('Home assignment'),
    keyword: await read('Keyword 1'),
    resource: await read('Lesson resource 1'),
    referenceTitle: await read('Reference 1 title'),
    referenceType: await selectLabel('Reference 1 type'),
    deepHope: deepCount ? await deepSel.first().inputValue().catch(() => null)
      : await selectLabel('Deep Hope'),
    storyline: await selectLabel('Storyline'),
    godsStory: await selectLabel("God's Story"),
    throughLines: through,
    wapefSectionVisible: (await page.getByText(/Teacher-selected values/i).count()) > 0,
  }
}

function snapshot(lesson) {
  return {
    lesson_topic: lesson.lesson_topic,
    introduction: lesson.introduction,
    assessment: lesson.assessment,
    conclusion: lesson.conclusion,
    class_assignment: lesson.class_assignment,
    home_assignment: lesson.home_assignment,
    keywords: lesson.keywords || [],
    teaching_learning_resources: lesson.teaching_learning_resources || [],
    source_tlrs: lesson.source_tlrs || [],
    references: (lesson.structured_references || []).map((r) => `${r.type}|${r.title}`),
    wapef_deep_hope: lesson.wapef_deep_hope,
    wapef_storyline: lesson.wapef_storyline,
    wapef_through_lines: lesson.wapef_through_lines || [],
    wapef_gods_story: lesson.wapef_gods_story,
    main_activities: (lesson.main_activities || []).map((a) => a.description),
    class_level: lesson.class_level,
    school_name: lesson.school_name,
    template_id: lesson.template_id,
  }
}

/** Save a browser download to disk and report what the bytes look like. */
async function saveDownload(page, label, action) {
  const target = path.join(OUT, label)
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    action(),
  ])
  await download.saveAs(target)
  const bytes = fs.readFileSync(target)
  return { path: target, size: bytes.length, head: bytes.subarray(0, 5).toString('binary') }
}

/** Read a DOCX's document.xml / a PDF's text + render evidence. */
function probeExport(file) {
  const py = path.join(ROOT, 'backend', 'venv', 'Scripts', 'python.exe')
  const script = `
import sys, zipfile, json, re
p = sys.argv[1]
out = {"kind": "unknown"}
if p.lower().endswith(".docx"):
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        tables = xml.count("<w:tbl>") + xml.count("<w:tbl ")
    out = {"kind": "docx", "text": re.sub(r"<[^>]+>", "", xml), "tables": tables}
else:
    import pymupdf as fitz
    doc = fitz.open(p)
    text = "\\n".join(pg.get_text() for pg in doc)
    drawings = sum(len(pg.get_drawings()) for pg in doc)
    out = {"kind": "pdf", "pages": doc.page_count, "text": text, "drawings": drawings}
print("@@PROBE@@" + json.dumps(out))
`
  const { execFileSync } = require('child_process')
  const raw = execFileSync(py, ['-c', script, file], { maxBuffer: 128 * 1024 * 1024 }).toString('utf-8')
  // The interpreter prints library warnings on stdout before our payload.
  const line = raw.split('\n').find((l) => l.startsWith('@@PROBE@@'))
  return JSON.parse(line.slice('@@PROBE@@'.length))
}

function renderPdfPages(file, prefix) {
  const py = path.join(ROOT, 'backend', 'venv', 'Scripts', 'python.exe')
  const script = `
import sys
import pymupdf as fitz
src, outdir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
doc = fitz.open(src)
written = []
for i, page in enumerate(doc):
    p = f"{outdir}/{prefix}-page{i+1}.png"
    page.get_pixmap(dpi=110).save(p)
    written.append(p)
print("\\n".join(written))
`
  const { execFileSync } = require('child_process')
  return execFileSync(py, ['-c', script, file, OUT, prefix], { maxBuffer: 64 * 1024 * 1024 })
    .toString('utf-8').trim().split('\n').filter(Boolean)
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
    // ── 1. Teacher account + school ───────────────────────────────────────
    await signup(page)
    log(true, 'fresh teacher account created', EMAIL)
    const schoolShown = await setSchoolInSettings(page)
    log(schoolShown === SCHOOL, 'school stored on the teacher profile (PART 7)', schoolShown)

    // ── 2. Real scheme through the real upload surface ────────────────────
    if (!fs.existsSync(SCHEME)) throw new Error(`scheme fixture missing: ${SCHEME}`)
    const schemeId = await uploadScheme(page)
    log(true, 'real Computing scheme uploaded and extracted through the UI', `scheme=${schemeId}`)
    await shot(page, '01-review.png')

    // ── 3. WAPEF template + allocation preview ────────────────────────────
    const { wapefLabel } = await configureWapef(page, { perWeek: '2' })
    log(/Approved WAPEF Plan/i.test(wapefLabel || ''),
      'Approved WAPEF Plan selected in the Template dropdown', wapefLabel)
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

    // ── 4. Generate → workspace says WAPEF ────────────────────────────────
    await generate(page)
    // A cold deploy serves the workspace shell before the lesson fetch
    // resolves; wait until the teacher's pre-generation selections are ON the
    // page (or the fields prove absent) instead of racing the fetch.
    let afterGenerate = await readWorkspace(page)
    for (let i = 0; i < 20 && (afterGenerate.deepHope !== picks.deepHope
        || afterGenerate.throughLines.length < 2); i += 1) {
      await sleep(1500)
      afterGenerate = await readWorkspace(page)
    }
    console.log(`[diag] post-generate workspace: ${JSON.stringify(afterGenerate._diag)},
      deepHope=${JSON.stringify((afterGenerate.deepHope || '').slice(0, 30))},
      through=${JSON.stringify(afterGenerate.throughLines)}`)
    // When do the stored lessons carry the selections? (read-after-write lag)
    // The generate URL carries the SCHEME id, so the job-scoped route
    // (/{job_id}/lessons) is the wrong key for it and answers 404 — poll the
    // scheme-scoped route, which returns the same lesson_plans payload.
    const jobMatch = page.url().match(/generate\/([a-f0-9-]+)/i)
    if (jobMatch) {
      const lessonsPath = jobMatch[1] === schemeId
        ? `/api/generation/schemes/${jobMatch[1]}/lessons`
        : `/api/generation/${jobMatch[1]}/lessons`
      for (let i = 0; i < 12; i += 1) {
        const jobLessons = await apiGet(page, lessonsPath)
        const jl = (jobLessons.body?.lesson_plans || [])[0] || {}
        console.log(`[diag] t+${i * 2}s stored-API deep=${jl.wapef_deep_hope ? 'SET' : 'EMPTY'} tmpl=${jl.template_id || 'none'}`)
        if (jl.wapef_deep_hope) break
        await sleep(2000)
      }
    }
    log(afterGenerate.wapefSectionVisible,
      'workspace shows the WAPEF fields section (template identity is WAPEF)')
    log(Boolean(afterGenerate.throughLines.length),
      'the workspace reflects the Through lines chosen before generation',
      afterGenerate.throughLines.join(', '))
    log(afterGenerate.deepHope === picks.deepHope,
      'Deep Hope set before generation survives into the workspace', afterGenerate.deepHope)
    const jobUrl = page.url()
    await shot(page, '04-workspace.png')

    // ── 5. Edit EVERYTHING the teacher owns ───────────────────────────────
    const edits = {
      topic: 'Input devices: manual and automatic',
      starter: 'Display pictures of a keyboard, mouse, touchscreen and barcode reader. Ask learners which they have used at home and record their answers in two columns: devices a person works and devices that work on their own.',
      main: 'Give each pair a labelled diagram of a keyboard and ask them to point to the home row, the function keys and the number pad, then explain which of the devices sends data to the computer automatically.',
      assessment: 'Give each pair four device cards and ask them to sort them as manual or automatic, giving one reason per card; ask two pairs to justify a borderline device and listen for the words manual and automatic used correctly.',
      conclusion: 'Learners state one manual and one automatic input device they used today and explain in one sentence why a hospital or a supermarket would choose the automatic one.',
      classAssignment: 'In pairs, learners classify a set of device pictures as manual or automatic and write one advantage and one disadvantage of each group; the teacher checks the reasons given.',
      homeAssignment: 'List three input devices used in your home or community. For each one write whether it is manual or automatic, what it is used for and one care you must take when using it.',
      keyword: 'manual and automatic input devices',
      resource: 'Touchscreen (corrected spelling)',
      referenceTitle: 'Computing Curriculum, Basic 7, pages 12-14',
    }
    const typed = await editEverything(page, { ...edits, ...picks })

    // The scheme's own resource record must be read-only on screen.
    const sourceChips = await workspace(page)
      .getByText(/From your scheme \(source — read only\)/i).count()
    log(sourceChips > 0, 'the source resource list is shown read-only beside the lesson list')

    // ── 6. Save ───────────────────────────────────────────────────────────
    const saveResult = await save(page)
    log(saveResult.saved, 'Save succeeds and reports the edits are stored')
    log(!saveResult.actionFailed, 'no "Action failed" / internal server error on Save')
    await shot(page, '05-saved.png')

    // ── 7. Server snapshot (the database is the authority) ────────────────
    const lessonsRes = await apiGet(page, `/api/generation/lessons`)
    const all = lessonsRes.body?.lesson_plans || []
    const mine = all.filter((l) => l.lesson_topic === edits.topic)
    log(mine.length >= 1, 'saved lesson is found through the API', `topic=${edits.topic}`)
    const lessonId = (mine[0] || all[0]).id
    const before = await apiGet(page, `/api/generation/lessons/${lessonId}`)
    const snapBefore = snapshot(before.body || {})
    log(snapBefore.lesson_topic === edits.topic, 'API returns the edited topic')
    log(snapBefore.wapef_deep_hope === picks.deepHope,
      'API returns the saved Deep Hope verbatim', snapBefore.wapef_deep_hope)
    log(snapBefore.wapef_storyline === picks.storyline,
      'API returns the saved Storyline verbatim', snapBefore.wapef_storyline)
    log(snapBefore.wapef_gods_story === picks.godsStory,
      "API returns the saved God's Story verbatim", snapBefore.wapef_gods_story)
    log(snapBefore.wapef_through_lines.length >= 2,
      'API returns BOTH saved Through lines', snapBefore.wapef_through_lines.join(' | '))
    log((snapBefore.teaching_learning_resources || []).includes(edits.resource),
      'API returns the corrected lesson resource', (snapBefore.teaching_learning_resources || []).join(', '))
    log(snapBefore.class_assignment === edits.classAssignment, 'API returns the Class Assignment')
    log(snapBefore.home_assignment === edits.homeAssignment, 'API returns the Home Assignment')
    log(snapBefore.school_name === SCHOOL, 'API returns the school on the lesson', snapBefore.school_name)
    log(snapBefore.template_id === 'tpl-wapef-approved-plan',
      'the lesson keeps the WAPEF template identity', String(snapBefore.template_id))

    const sourceBefore = JSON.stringify(snapBefore.source_tlrs)

    // ── 8. Leave, return, reload ──────────────────────────────────────────
    await page.goto(`${WEB}/dashboard`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    await shot(page, '06-dashboard.png')
    await page.goto(`${WEB}/lessons`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    await shot(page, '07-lessons.png')
    await page.goto(jobUrl, { waitUntil: 'domcontentloaded', timeout: 90000 })
    await page.locator('[data-lesson-workspace]').waitFor({ timeout: 120000 })
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 90000 })
    await page.locator('[data-lesson-workspace]').waitFor({ timeout: 120000 })
    await page.waitForTimeout(1500)

    // Same cold-fetch race as after generation: the saved topic is the signal
    // that the lesson data has actually arrived.
    let afterReload = await readWorkspace(page)
    for (let i = 0; i < 20 && afterReload.lessonTopic !== edits.topic; i += 1) {
      await sleep(1500)
      afterReload = await readWorkspace(page)
    }
    const checks = [
      ['lesson topic', afterReload.lessonTopic, edits.topic],
      ['Phase 1 starter', afterReload.starter, edits.starter],
      ['Main Learning', afterReload.main, edits.main],
      ['Assessment', afterReload.assessment, edits.assessment],
      ['Phase 3 reflection', afterReload.conclusion, edits.conclusion],
      ['Class Assignment', afterReload.classAssignment, edits.classAssignment],
      ['Home Assignment', afterReload.homeAssignment, edits.homeAssignment],
      ['keyword', afterReload.keyword, edits.keyword],
      ['lesson resource', afterReload.resource, edits.resource],
      ['reference title', afterReload.referenceTitle, edits.referenceTitle],
      ['reference type', afterReload.referenceType, typed.referenceType],
      ['Deep Hope', afterReload.deepHope, picks.deepHope],
      ['Storyline', afterReload.storyline, picks.storyline],
      ["God's Story", afterReload.godsStory, picks.godsStory],
    ]
    for (const [label, got, want] of checks) {
      log(got === want, `${label} survives leave → return → reload`,
        got === want ? undefined : `got ${JSON.stringify(got)} want ${JSON.stringify(want)}`)
    }
    log(afterReload.throughLines.length >= 2,
      'both Through lines survive leave → return → reload',
      afterReload.throughLines.join(' | '))
    await shot(page, '08-after-reload.png')

    // The database agrees, and the SOURCE resources were never touched.
    const after = await apiGet(page, `/api/generation/lessons/${lessonId}`)
    const snapAfter = snapshot(after.body || {})
    log(JSON.stringify(snapAfter.source_tlrs) === sourceBefore,
      'the scheme\'s own source resource record is unchanged (PART 13)',
      snapAfter.source_tlrs.join(', '))
    const same = ['lesson_topic', 'introduction', 'assessment', 'conclusion',
      'class_assignment', 'home_assignment', 'wapef_deep_hope', 'wapef_storyline',
      'wapef_gods_story', 'class_level', 'school_name', 'template_id']
      .every((k) => snapAfter[k] === snapBefore[k])
    log(same, 'every stored field is identical before and after the navigation round-trip')
    log(JSON.stringify(snapAfter.wapef_through_lines) === JSON.stringify(snapBefore.wapef_through_lines),
      'Through lines are identical before and after the round-trip')

    // ── 9. The /lessons/{id} surface shows the same lesson ────────────────
    await page.goto(`${WEB}/lessons/${lessonId}`, { waitUntil: 'domcontentloaded', timeout: 90000 })
    await page.waitForTimeout(2500)
    // The lesson page holds its values in inputs, so read them, not innerText.
    const pageTopic = await page.locator('#lesson-topic').inputValue().catch(() => null)
    const pageStarter = await page.locator('#lesson-introduction').inputValue().catch(() => null)
    log(pageTopic === edits.topic,
      'the lesson page shows the saved topic', String(pageTopic))
    log(pageStarter === edits.starter,
      'the lesson page shows the saved Phase 1 starter')
    await shot(page, '09-lesson-page.png')

    // ── 10. DOCX + PDF exports carry the lesson ───────────────────────────
    await page.goto(jobUrl, { waitUntil: 'domcontentloaded', timeout: 90000 })
    await page.locator('[data-lesson-workspace]').waitFor({ timeout: 120000 })
    await page.waitForTimeout(1000)

    const docx = await saveDownload(page, 'lesson.docx', () =>
      page.getByRole('button', { name: /export docx/i }).first().click())
    log(docx.head.startsWith('PK'), 'DOCX export downloads a real package', `${docx.size} bytes`)
    const docxProbe = probeExport(docx.path)
    // Extracted text wraps and merges runs, so compare on collapsed whitespace.
    const norm = (s) => String(s).replace(/\s+/g, ' ')
    const docxText = norm(docxProbe.text || '')
    log(docxText.includes(norm(edits.topic)), 'DOCX carries the saved topic')
    log(docxText.includes(norm(picks.deepHope)), 'DOCX carries the saved Deep Hope verbatim')
    log(docxText.includes(norm(picks.storyline)), 'DOCX carries the saved Storyline verbatim')
    log(docxText.includes(norm(picks.godsStory)), "DOCX carries the saved God's Story verbatim")
    log(docxText.includes(norm(chosenThrough[0])),
      'DOCX carries the saved Through line', chosenThrough[0])
    log(docxText.includes(norm(edits.classAssignment)),
      'DOCX carries the Class Assignment verbatim')
    log(docxText.includes(norm(edits.homeAssignment)),
      'DOCX carries the Home Assignment verbatim')
    log(/Touchscreen/.test(docxText), 'DOCX carries the corrected lesson resource')
    log(/In pairs, learners classify/.test(docxText),
      'DOCX keeps the assignment sentence punctuation (not a comma-less list)')
    log((docxProbe.tables || 0) >= 3,
      'DOCX contains the template\'s real tables', `${docxProbe.tables} tables`)
    log(!/Acceptance|svgSuggest|test marker|fixture marker/i.test(docxText),
      'DOCX contains no internal or debug text')

    const pdf = await saveDownload(page, 'lesson.pdf', () =>
      page.getByRole('button', { name: /export pdf/i }).first().click())
    log(pdf.head.startsWith('%PDF-'), 'PDF export downloads a real PDF', `${pdf.size} bytes`)
    const pdfProbe = probeExport(pdf.path)
    const pdfText = norm(pdfProbe.text || '')
    log((pdfProbe.pages || 0) >= 1, 'PDF has at least one page', `${pdfProbe.pages} pages`)
    log(pdfText.includes(norm(edits.topic)), 'PDF carries the saved topic')
    log(pdfText.includes(norm(picks.deepHope)), 'PDF carries the saved Deep Hope verbatim')
    log(pdfText.includes(norm(picks.storyline)), 'PDF carries the saved Storyline verbatim')
    log(pdfText.includes(norm(picks.godsStory)), "PDF carries the saved God's Story verbatim")
    log(pdfText.includes(norm(chosenThrough[0])), 'PDF carries the saved Through line')
    log(pdfText.includes(norm(edits.classAssignment)),
      'PDF carries the Class Assignment verbatim')
    log(pdfText.includes(norm(edits.homeAssignment)),
      'PDF carries the Home Assignment verbatim')
    log(/Touchscreen/.test(pdfText), 'PDF carries the corrected lesson resource')
    log(/In pairs, learners classify/.test(pdfText),
      'PDF keeps the assignment sentence punctuation (not a comma-less list)')
    log(!/Acceptance|svgSuggest|test marker|fixture marker/i.test(pdfText),
      'PDF contains no internal or debug text')
    log((pdfProbe.drawings || 0) > 20,
      'PDF draws real table rules/borders (not a text dump)', `${pdfProbe.drawings} vector drawings`)

    // PHASE 11 — render the pages so the layout itself can be inspected.
    const pages = renderPdfPages(pdf.path, 'pdf')
    log(pages.length >= 1, 'PDF pages rendered to images for visual inspection',
      pages.map((p) => path.basename(p)).join(', '))
    fs.writeFileSync(path.join(OUT, 'pdf-text.txt'), pdfProbe.text || '')

    log(httpErrors.length === 0, 'no HTTP errors during the journey',
      httpErrors.slice(0, 3).join(' | '))
    log(pageErrors.length === 0, 'no uncaught page exceptions',
      pageErrors.slice(0, 3).join(' | '))
  } catch (e) {
    log(false, 'journey completed', e.message.split('\n')[0])
    await shot(page, '99-failure.png')
  } finally {
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n') + '\n')
    console.log(`\n${pass} passed, ${fail} failed — artefacts in e2e/lesson-persistence-journey/`)
    await browser.close()
    process.exit(fail === 0 ? 0 : 1)
  }
})()
