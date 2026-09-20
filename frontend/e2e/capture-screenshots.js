// Recapture docs/screenshots 08-11 from the live local production build.
const { chromium } = require('playwright');
const path = require('path');

const BASE = 'http://localhost:3000';
const PASSWORD = 'Accept#2026';
const OUT = path.resolve(__dirname, '../../docs/screenshots');

async function login(page, entryPath, email, waitText) {
  await page.goto(BASE + entryPath, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.getByText(waitText).first().waitFor({ timeout: 15000 });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2500);
}

async function clearSession(page) {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.context().clearCookies();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // 08 — School Admin dashboard
  await clearSession(page);
  await login(page, '/login/school-admin', 'accept.sa@schemeknit.test', 'SchemeKnit School Administration');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, '08-school-admin.png') });
  console.log('captured 08-school-admin.png');

  // 09 — Platform Admin dashboard
  await clearSession(page);
  await login(page, '/login/platform-admin', 'accept.pa@schemeknit.test', 'SchemeKnit Platform Administration');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '09-platform-admin.png') });
  console.log('captured 09-platform-admin.png');

  // 10 — Multi-subject detection confirmation (teacher)
  await clearSession(page);
  await login(page, '/login', 'accept.teacher@schemeknit.test', 'SchemeKnit Teacher');
  await page.goto(BASE + '/upload', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.getByRole('heading', { name: 'Upload Your Scheme of Work' }).waitFor({ timeout: 15000 });
  await page.locator('input[type="file"]').setInputFiles(path.resolve(__dirname, '../../temp/accept-multi-subject.docx'));
  await page.getByRole('button', { name: 'Upload & Process' }).click();
  await page.getByText('Multiple subjects detected').waitFor({ timeout: 30000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, '10-multi-subject-detect.png') });
  console.log('captured 10-multi-subject-detect.png');

  // 11 — Subject confirmed → review of the Science section
  await page.getByRole('button', { name: /^Science/ }).click();
  await page.waitForURL(/\/review\//, { timeout: 30000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, '11-multi-subject-generated.png') });
  console.log('captured 11-multi-subject-generated.png');

  await browser.close();
})().catch((e) => { console.error('ERROR', e.message); process.exit(1); });
