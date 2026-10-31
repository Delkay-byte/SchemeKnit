// Phase 11.7 — Guided lesson configuration browser acceptance.
//
// The teacher journey this round adds:
//  1. Review page shows the ONE "Configure lesson rubrics" button.
//  2. The modal opens with the seven fields.
//  3. Save persists to the server; the server reports readiness.
//  4. Reload restores the saved configuration (Phase 2.3 persistence).
//  5. Cancel (dirty) does not silently discard; second Cancel keeps saved
//     values.
//  6. The generate page carries the single configuration entry point.
//
// Env: TF_WEB_URL (default http://localhost:3000), TF_API_URL (default
// http://localhost:8000). Uses the real uploaded Basic 9 Science scheme.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3000').replace(/\/$/, '');
const API = (process.env.TF_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const ROOT = path.join(__dirname, '..', '..');
const SCIENCE = path.join(ROOT, 'backend', 'uploads',
  '1d3813d1-8fce-47b1-ac81-2ab40c5a8bb8_BASIC 9 SCIENCE SCHEME OF LEARNING.docx');
const OUT = path.join(__dirname, 'lesson-config-acceptance');
fs.mkdirSync(OUT, { recursive: true });

const STAMP = Date.now();
const PASS_W = 'Auto#2026';
const EMAIL = `lesson.config.${STAMP}@schemeknit.test`;
const NAME = 'Config Acceptance';
const SCHOOL = 'Kpogede Community School';

let pass = 0, fail = 0;
const results = [];
function log(ok, label, detail) {
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  — ${detail}` : ''}`);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  — ${detail}` : ''}`);
  if (ok) pass++; else fail++;
}
let page = null; // set once the browser context is created (used by check diagnostics)

async function check(fn, label, detail) {
  try {
    const d = await fn();
    log(true, label, typeof d === 'string' ? d : detail);
    return d;
  } catch (e) {
    log(false, label, `${detail || ''} :: ${String(e.message || e).slice(0, 300)}`);
    try {
      await page.screenshot({ path: path.join(OUT, `fail-${label.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.png`) });
      console.log('   page URL at failure:', page.url());
      const bodyText = (await page.locator('body').textContent().catch(() => '')) || '';
      console.log('   page text head:', bodyText.replace(/\s+/g, ' ').slice(0, 220));
    } catch { /* diagnostics never mask the result */ }
    return null;
  }
}

async function waitHydrated(page, probe, timeout = 30000) {
  const start = Date.now();
  const probeValue = `hydration-probe-${Date.now().toString(36)}`;
  while (Date.now() - start < timeout) {
    const filled = await page.evaluate(({ sel, value }) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value')?.set;
      if (setter) setter.call(el, value); else el.value = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return el.value === value;
    }, { sel: probe, value: probeValue });
    if (filled) return true;
    await page.waitForTimeout(250);
  }
  throw new Error(`never hydrated: ${probe}`);
}

async function apiGet(page, url) {
  return page.evaluate(async (u) => {
    const t = window.sessionStorage.getItem('teachflow_token');
    const r = await fetch(u, { headers: { Authorization: 'Bearer ' + t } });
    return r.ok ? r.json() : { error: r.status };
  }, url);
}

async function fillStable(page, sel, value, tries = 6) {
  // Late hydration remounts controlled inputs and wipes pre-hydration
  // values; fill and re-fill until the value survives a settle delay.
  for (let i = 0; i < tries; i++) {
    await page.fill(sel, value);
    await page.waitForTimeout(900);
    if ((await page.inputValue(sel)) === value) return;
  }
  throw new Error(`value never stuck in ${sel}`);
}

(async () => {
  const browser = await chromium.launch();
  page = await (await browser.newContext({ viewport: { width: 1360, height: 900 } })).newPage();

  // Signup through the real UI (same flow as zeli-method-journey).
  await check(async () => {
    await page.goto(`${WEB}/signup`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('#signup-name').waitFor({ timeout: 30000 });
    await fillStable(page, '#signup-name', NAME);
    await fillStable(page, '#signup-email', EMAIL);
    await fillStable(page, '#signup-password', PASS_W);
    await fillStable(page, '#signup-confirm', PASS_W);
    await page.getByRole('button', { name: /create account/i }).click();
    await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 60000 });
    return 'signed up via UI';
  }, 'signup via browser');

  // The teacher states their school once on the profile (independent
  // teachers start with none) — the configuration modal prepopulates it.
  await check(async () => {
    await page.goto(`${WEB}/settings`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('#profile-school').waitFor({ timeout: 30000 });
    await fillStable(page, '#profile-school', SCHOOL);
    await page.getByRole('button', { name: /save profile/i }).click();
    await page.waitForTimeout(1200);
    return 'school saved on profile';
  }, 'school name on profile');

  // Upload the real scheme and continue to review.
  let schemeId = null;
  await check(async () => {
    await page.goto(`${WEB}/upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    // A file input's value can never be set programmatically, so hydration
    // is verified via the upload button instead. The input itself is
    // visually hidden (class="hidden") — wait for it attached.
    await page.locator('input[type="file"]').waitFor({ state: 'attached', timeout: 30000 });
    await page.locator('input[type="file"]').setInputFiles(SCIENCE);
    await page.getByRole('button', { name: /upload & process/i }).click();
    await page.waitForSelector('[data-upload-success]', { timeout: 180000 });
    const review = page.getByRole('button', { name: /review curriculum/i });
    if (await review.count()) await review.click();
    await page.waitForURL(/\/review\//, { timeout: 90000 });
    schemeId = page.url().match(/review\/([^/?]+)/)[1];
    return `scheme ${schemeId}`;
  }, 'upload + extraction + review');

  // 1. Exactly ONE "Configure lesson rubrics" button on the review page.
  await check(async () => {
    const btn = page.locator('[data-configure-lesson-rubrics]');
    await btn.waitFor({ timeout: 30000 });
    const text = (await btn.textContent() || '').trim();
    if (!text.includes('Configure lesson rubrics')) throw new Error(`label "${text}"`);
    const count = await btn.count();
    if (count !== 1) throw new Error(`${count} buttons`);
    return 'exactly one, exact label';
  }, 'review page: single "Configure lesson rubrics" button');

  // 2. The modal opens with the seven fields.
  await check(async () => {
    await page.click('[data-configure-lesson-rubrics]');
    await page.waitForSelector('[data-lesson-config-modal]', { timeout: 15000 });
    for (const id of ['lcfg-school', 'lcfg-teacher', 'lcfg-class-size',
      'lcfg-duration', 'lcfg-reference', 'lcfg-periods', 'lcfg-period']) {
      if (!(await page.locator(`#${id}`).count())) throw new Error(`missing #${id}`);
    }
    if (!(await page.locator('[data-lesson-config-modal] button:has-text("Monday")').count())) {
      throw new Error('missing teaching-day control');
    }
    return 'all seven fields present';
  }, 'modal opens with all fields');

  // 3. Save persists; the SERVER reports ready.
  await check(async () => {
    await page.fill('#lcfg-school', SCHOOL);
    await page.fill('#lcfg-teacher', NAME);
    await page.fill('#lcfg-class-size', '31');
    await page.fill('#lcfg-duration', '60');
    await page.fill('#lcfg-reference', 'Basic 9 Science Curriculum (NaCCA)');
    await page.fill('#lcfg-periods', '3');
    await page.fill('#lcfg-period', '1st & 2nd');
    for (const day of ['Monday', 'Wednesday', 'Thursday']) {
      await page.click(`[data-lesson-config-modal] button:has-text("${day}")`);
    }
    await page.click('[data-save-lesson-config]');
    await page.waitForSelector('[data-lesson-config-modal]', { state: 'detached', timeout: 20000 });
    const body = await apiGet(page, `${API}/api/generation/${schemeId}/lesson-config`);
    if (body.error) throw new Error(`readback ${body.error}`);
    if (body.config.class_size !== 31) throw new Error(`class_size ${body.config.class_size}`);
    if (!body.ready) throw new Error(`not ready: ${body.missing}`);
    return 'server reports ready, class_size 31';
  }, 'save persists and reports ready');

  // 4. Reload restores the saved configuration.
  await check(async () => {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('[data-configure-lesson-rubrics]').waitFor({ timeout: 30000 });
    await page.click('[data-configure-lesson-rubrics]');
    await page.waitForSelector('#lcfg-class-size', { timeout: 15000 });
    const size = await page.inputValue('#lcfg-class-size');
    const school = await page.inputValue('#lcfg-school');
    if (size !== '31') throw new Error(`class size "${size}"`);
    if (school !== SCHOOL) throw new Error(`school "${school}"`);
    return 'values survive reload';
  }, 'reload restores saved configuration');

  // 5. Cancel keeps the last saved configuration (dirty Cancel arms first).
  await check(async () => {
    await page.fill('#lcfg-class-size', '45');
    await page.locator('[data-lesson-config-modal] button:has-text("Cancel")').click();
    // First cancel arms; the modal stays open with the discard warning.
    await page.waitForSelector('[data-lesson-config-modal]', { timeout: 5000 });
    await page.locator('[data-lesson-config-modal] button:has-text("Cancel")').click();
    await page.waitForSelector('[data-lesson-config-modal]', { state: 'detached', timeout: 5000 });
    const saved = await apiGet(page, `${API}/api/generation/${schemeId}/lesson-config`);
    if (saved.config.class_size !== 31) throw new Error(`leaked ${saved.config.class_size}`);
    return 'cancel never saved the draft';
  }, 'cancel preserves last saved configuration');

  // 6. Generate page: the single configuration entry point is there.
  await check(async () => {
    await page.goto(`${WEB}/generate/${schemeId}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('[data-configure-lesson-rubrics]').waitFor({ timeout: 45000 });
    const count = await page.locator('[data-configure-lesson-rubrics]').count();
    if (count !== 1) throw new Error(`${count} buttons`);
    return 'generate page carries the single configuration entry point';
  }, 'generate page: one configuration entry point');

  await browser.close();
  fs.writeFileSync(path.join(OUT, `result-${STAMP}.txt`), results.join('\n'));
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
