/**
 * Responsive + axe acceptance for the hardened critical screens.
 * Uses disposable local fixtures; no production data.
 *
 * Env: UX_WEB_URL, UX_API_URL, UX_TEACHER_TOKEN, UX_TEACHER_USER,
 *      UX_ADMIN_TOKEN, UX_ADMIN_USER, UX_LESSON_ID, UX_PLAN_ID, UX_SCHEME_ID
 */
const { chromium } = require('playwright')
const path = require('path')

const WEB = process.env.UX_WEB_URL || 'http://127.0.0.1:3100'
const LESSON_ID = process.env.UX_LESSON_ID
const PLAN_ID = process.env.UX_PLAN_ID || 'wp-ux-fixture'
const SCHEME_ID = process.env.UX_SCHEME_ID
const WIDTHS = [320, 360, 390, 768, 1024, 1280, 1440]
const results = []

function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

async function makeContext(browser, token, user, width) {
  const context = await browser.newContext({ viewport: { width, height: 900 } })
  await context.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token, user })
  return context
}

async function axe(page, label) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const report = await page.evaluate(async () => {
    return await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] },
    })
  })
  const serious = report.violations.filter((v) => ['critical', 'serious'].includes(v.impact))
  record(`axe ${label}`, serious.length === 0,
    serious.map((v) => `${v.id}:${v.nodes.length}`).join(', '))
}

async function main() {
  const browser = await chromium.launch()
  const teacherToken = process.env.UX_TEACHER_TOKEN
  const teacherUser = JSON.parse(process.env.UX_TEACHER_USER || '{}')
  const adminToken = process.env.UX_ADMIN_TOKEN
  const adminUser = JSON.parse(process.env.UX_ADMIN_USER || '{}')

  const screens = [
    { label: 'dashboard', role: 'teacher', url: '/dashboard' },
    { label: 'lesson editor', role: 'teacher', url: `/lessons/${LESSON_ID}` },
    { label: 'weekly plan editor', role: 'teacher', url: `/weekly-plans/${PLAN_ID}` },
    { label: 'new weekly plan', role: 'teacher', url: '/weekly-plans/new' },
    { label: 'review/scheme', role: 'teacher', url: `/review/${SCHEME_ID}` },
    { label: 'settings', role: 'teacher', url: '/settings' },
    { label: 'school overview', role: 'admin', url: '/school-admin' },
    { label: 'teacher management', role: 'admin', url: '/school-admin/teachers' },
    { label: 'school settings', role: 'admin', url: '/school-admin/settings' },
    { label: 'licence management', role: 'admin', url: '/school-admin/license' },
  ]

  for (const width of WIDTHS) {
    const teacherContext = await makeContext(browser, teacherToken, teacherUser, width)
    const teacherPage = await teacherContext.newPage()
    const adminContext = await makeContext(browser, adminToken, adminUser, width)
    const adminPage = await adminContext.newPage()

    for (const screen of screens) {
      const page = screen.role === 'teacher' ? teacherPage : adminPage
      await page.goto(WEB + screen.url, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(700)
      const noOverflow = await page.evaluate(() =>
        document.documentElement.scrollWidth <= window.innerWidth + 1)
      const hasBody = (await page.locator('body').innerText()).trim().length > 10
      record(`${screen.label} @${width}`, noOverflow && hasBody,
        noOverflow ? '' : 'horizontal overflow')

      if (width === 1280) {
        await axe(page, screen.label)
      }
    }

    if (width === 1280) {
      await teacherPage.goto(`${WEB}/review/${SCHEME_ID}`, { waitUntil: 'domcontentloaded' })
      const open = teacherPage.getByRole('button', { name: /Configure lesson rubrics/i }).first()
      await open.waitFor({ timeout: 20000 })
      await open.click()
      await teacherPage.getByRole('dialog').waitFor({ timeout: 10000 })
      record('lesson config modal opens', await teacherPage.getByRole('dialog').isVisible())
      await axe(teacherPage, 'lesson config modal')
      await teacherPage.keyboard.press('Escape')
    }

    await teacherContext.close()
    await adminContext.close()
  }

  // Draft recovery banner at the narrowest width.
  const ctx = await makeContext(browser, teacherToken, teacherUser, 320)
  const page = await ctx.newPage()
  await page.goto(`${WEB}/weekly-plans/new`, { waitUntil: 'domcontentloaded' })
  const week = page.getByLabel('Week number')
  await week.waitFor({ timeout: 20000 })
  await page.waitForTimeout(800)
  await week.fill('6')
  await page.waitForTimeout(1300)
  await page.reload({ waitUntil: 'domcontentloaded' })
  const recovered = await page.getByText(/We found your unsaved work/).first()
    .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false)
  const noOverflow = await page.evaluate(() =>
    document.documentElement.scrollWidth <= window.innerWidth + 1)
  record('draft banner @320 readable and contained', recovered && noOverflow)
  await ctx.close()

  // Reduced motion on a loading skeleton.
  const reduced = await browser.newContext({ reducedMotion: 'reduce', viewport: { width: 390, height: 844 } })
  await reduced.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: teacherToken, user: teacherUser })
  const reducedPage = await reduced.newPage()
  await reducedPage.route('**/api/documents/', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    await route.continue()
  })
  await reducedPage.goto(`${WEB}/dashboard`, { waitUntil: 'domcontentloaded' })
  await reducedPage.getByText('Loading your dashboard').waitFor({ state: 'attached', timeout: 5000 }).catch(() => {})
  const animation = await reducedPage.locator('[aria-busy="true"] .animate-pulse').first()
    .evaluate((el) => getComputedStyle(el).animationName).catch(() => 'missing')
  record('reduced motion disables skeleton animation', animation === 'none', animation)
  await reduced.close()

  await browser.close()
  const failed = results.filter((r) => !r.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
}).finally(() => setTimeout(() => process.exit(process.exitCode || 0), 500))
