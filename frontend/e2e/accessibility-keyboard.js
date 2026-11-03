/** Keyboard/focus checks for the critical dialogs and recovery page. */
const { chromium } = require('playwright')

const WEB = process.env.UX_WEB_URL || 'http://127.0.0.1:3100'
const SCHEME_ID = process.env.UX_SCHEME_ID
const results = []
function record(name, passed, detail = '') {
  results.push({ name, passed, detail })
  console.log(`${passed ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await context.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, {
    token: process.env.UX_TEACHER_TOKEN,
    user: JSON.parse(process.env.UX_TEACHER_USER || '{}'),
  })
  const page = await context.newPage()

  await page.goto(`${WEB}/review/${SCHEME_ID}`, { waitUntil: 'domcontentloaded' })
  const trigger = page.getByRole('button', { name: /Configure lesson rubrics/i }).first()
  await trigger.waitFor({ timeout: 20000 })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog')
  await dialog.waitFor({ timeout: 10000 })
  const focusInside = await page.evaluate(() =>
    Boolean(document.querySelector('[role="dialog"]')?.contains(document.activeElement)))
  record('dialog receives keyboard focus', focusInside)

  for (let i = 0; i < 6; i += 1) await page.keyboard.press('Tab')
  const stillInside = await page.evaluate(() =>
    Boolean(document.querySelector('[role="dialog"]')?.contains(document.activeElement)))
  record('dialog keeps keyboard focus contained', stillInside)

  await page.keyboard.press('Escape')
  await dialog.waitFor({ state: 'detached', timeout: 5000 }).catch(() => {})
  const restored = await page.evaluate(() =>
    document.activeElement?.textContent?.includes('Configure lesson rubrics') || false)
  record('focus returns to the trigger after Escape', restored)

  await page.goto(`${WEB}/this-route-does-not-exist`, { waitUntil: 'domcontentloaded' })
  await page.keyboard.press('Tab')
  const focus = await page.evaluate(() => {
    const el = document.activeElement
    const style = el ? getComputedStyle(el) : null
    return {
      text: el?.textContent?.trim().slice(0, 40),
      visible: Boolean(style && (style.outlineStyle !== 'none' || style.boxShadow !== 'none')),
    }
  })
  record('not-found first keyboard target is actionable', /Go to dashboard/i.test(focus.text || ''), focus.text)
  record('keyboard focus indicator is visible', focus.visible)

  await browser.close()
  const failed = results.filter((r) => !r.passed)
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
}).finally(() => setTimeout(() => process.exit(process.exitCode || 0), 500))
