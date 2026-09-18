/**
 * CORS isolation: fetch DOCX vs PDF from inside the page (real browser CORS
 * pipeline) and report per-request ACAO presence + timing.
 */
const { chromium } = require('playwright')
const WEB = process.env.TF_WEB_URL || 'http://localhost:3000'
const TEACHER = { email: 'teacher@acceptance.test', password: 'TeacherPass123' }
const JOB_ID = process.env.TF_JOB_ID || '47f19a86-50fb-45d4-9cf6-56cc97fb2cf7'

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome' })
  const page = await (await browser.newContext()).newPage()
  await page.goto(`${WEB}/login/`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[type="email"]', TEACHER.email)
  await page.fill('input[type="password"]', TEACHER.password)
  await page.click('button[type="submit"]')
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })

  const result = await page.evaluate(async (jobId) => {
    // Pull the token the same way the app does
    const token = localStorage.getItem('teachflow_token') ||
                  localStorage.getItem('token') || localStorage.getItem('auth_token') ||
                  sessionStorage.getItem('teachflow_token') || sessionStorage.getItem('token') ||
                  sessionStorage.getItem('auth_token') || ''
    const headers = token ? { Authorization: `Bearer ${token.replace(/"/g, '')}` } : {}
    const out = []
    for (const kind of ['docx', 'pdf']) {
      const t0 = Date.now()
      try {
        const res = await fetch(
          `http://localhost:8000/api/generation/${jobId}/export/${kind}?template_type=GES-style&template_id=tpl-approved-org-headteacher`,
          { method: 'POST', headers })
        const buf = await res.arrayBuffer()
        out.push({
          kind, status: res.status, ms: Date.now() - t0,
          acao: res.headers.get('access-control-allow-origin'),
          ctype: res.headers.get('content-type'),
          bytes: buf.byteLength,
        })
      } catch (e) {
        out.push({ kind, error: String(e), ms: Date.now() - t0 })
      }
    }
    return out
  }, JOB_ID)
  console.log(JSON.stringify(result, null, 2))
  await browser.close().catch(() => {})
})().catch((e) => { console.error('failed:', e.message); process.exit(1) })
