// Browser acceptance: SCHOOL ADMIN + PLATFORM ADMIN dashboards (§1, §2).
// - /login/platform-admin loads directly and authenticates
// - /setup/platform-admin is protected (disabled after bootstrap)
// - Both dashboards render the canonical SchemeKnit SVG mark
// - Admin/setup routes carry noindex metadata
const { chromium } = require('playwright');

const BASE = 'http://localhost:3000';
const PASSWORD = 'Accept#2026';

let pass = 0, fail = 0;
async function check(fn, label) {
  let ok = false;
  try { ok = await fn(); } catch (e) { ok = false; }
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (ok) pass++; else fail++;
  return ok;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  // ── Platform Admin: direct login route (bypassing landing) ───────
  await page.goto(BASE + '/login/platform-admin', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.getByText('SchemeKnit Platform Administration').waitFor({ timeout: 15000 });
  await check(async () => true, 'platform-admin: direct login route loads');
  await page.locator('input[type="email"]').fill('accept.pa@schemeknit.test');
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL(/\/platform-admin/, { timeout: 20000 }).catch(() => {});
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await check(async () => page.url().includes('/platform-admin'), 'platform-admin: authentication succeeds → console');
  await check(async () => await page.locator('header svg').first().isVisible(), 'platform-admin dashboard: brand SVG mark renders');
  const paBox = await page.locator('header svg').first().boundingBox();
  await check(async () => paBox && paBox.width > 10, 'platform-admin dashboard: logo has real rendered size');

  // ── Setup protection: second PA setup must be unavailable ────────
  await page.goto(BASE + '/setup/platform-admin', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  const setupText = await page.evaluate(() => document.body.innerText);
  const setupDisabled = /not available|disabled|already (been )?(set up|created|provisioned)|no longer/i.test(setupText)
    || (await page.locator('form button[type="submit"]:not([disabled])').count() === 0 && setupText.length < 2000);
  await check(async () => setupDisabled, 'platform-admin: setup unavailable after bootstrap');

  // Clear the platform-admin session before the school-admin leg: a live
  // session redirects the login page to its console.
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.context().clearCookies();

  // ── School Admin dashboard ────────────────────────────────────────
  await page.goto(BASE + '/login/school-admin', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.getByText('SchemeKnit School Administration').first().waitFor({ timeout: 15000 });
  await page.locator('input[type="email"]').fill('accept.sa@schemeknit.test');
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL(/\/school-admin/, { timeout: 20000 }).catch(() => {});
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  await check(async () => page.url().includes('/school-admin'), 'school-admin: authentication succeeds → console');
  await check(async () => await page.locator('header svg').first().isVisible(), 'school-admin dashboard: brand SVG mark renders');
  const saBox = await page.locator('header svg').first().boundingBox();
  await check(async () => saBox && saBox.width > 10, 'school-admin dashboard: logo has real rendered size');
  await check(async () => await page.locator('header a[aria-label*="WhatsApp"]').count() > 0, 'school-admin: WhatsApp contact available');

  // ── noindex metadata on admin routes ─────────────────────────────
  // Clear the school-admin session: a live session redirects the login page.
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.context().clearCookies();
  // Trailing slash avoids the 308 that strips SSR evaluation locally.
  await page.goto(BASE + '/login/platform-admin/', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  const robots = await page.evaluate(() => {
    const m = document.querySelector('meta[name="robots"]');
    return m ? m.getAttribute('content') : null;
  });
  await check(async () => robots && /noindex/i.test(robots), 'platform-admin login route: noindex metadata');

  await browser.close();
  console.log(`\nADMIN DASHBOARDS: ${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error('ERROR', e.message); process.exit(2); });
