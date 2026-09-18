/**
 * Generate ALL raster brand assets from the clean vector SVG.
 * Uses Playwright (Chromium) as a high-quality SVG renderer.
 *
 * Outputs:
 *   - favicon.ico (16/32/48 multi-size)
 *   - PWA icons 72-512
 *   - Maskable icons 192/512 (navy bg + safe zone)
 *   - apple-touch-icon 180
 *   - Windows ICO (16-256)
 *   - social-preview.png, og-image.png
 *   - Verification comparison vs original logo
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BRAND = path.join(__dirname, '..', 'assets', 'brand');
const ICONS = path.join(__dirname, 'public', 'icons');
const PREVIEW = path.join(__dirname, '_brand_preview');
fs.mkdirSync(ICONS, { recursive: true });
fs.mkdirSync(PREVIEW, { recursive: true });

const MARK_SVG = fs.readFileSync(path.join(BRAND, 'schemeknit-mark.svg'), 'utf-8');
const WORDMARK_SVG = fs.readFileSync(path.join(BRAND, 'schemeknit-wordmark.svg'), 'utf-8');

const NAVY = '#102A43';
const CYAN = '#04A9CE';

/** Render an SVG string to a PNG buffer at a given pixel size (transparent bg). */
async function renderSvg(page, svg, size) {
  const escaped = svg.replace(/"/g, '\\"').replace(/\n/g, '');
  await page.setContent(`
    <html><body style="margin:0;padding:0;">
      <div style="width:${size}px;height:${size}px;">${svg}</div>
    </body></html>
  `, { waitUntil: 'load' });
  const el = await page.$('div');
  return el.screenshot({ type: 'png', omitBackground: true });
}

/** Render the mark on a solid navy background (for maskable icons). */
async function renderMaskable(page, size, bg, scale) {
  await page.setContent(`
    <html><body style="margin:0;padding:0;background:${bg};">
      <div style="width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;">
        <div style="width:${size * scale}px;height:${size * scale}px;">${MARK_SVG}</div>
      </div>
    </body></html>
  `, { waitUntil: 'load' });
  const el = await page.$('body > div');
  return el.screenshot({ type: 'png' });
}

/** Render the mark + wordmark composition for social/OG images. */
async function renderSocial(page, width, height) {
  await page.setContent(`
    <html><body style="margin:0;padding:0;background:${NAVY};width:${width}px;height:${height}px;">
      <div style="width:${width}px;height:${height}px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:40px;">
        <div style="width:${height * 0.42}px;height:${height * 0.42}px;">${MARK_SVG}</div>
        <div style="width:${width * 0.62}px;height:auto;">${WORDMARK_SVG}</div>
      </div>
    </body></html>
  `, { waitUntil: 'load' });
  const el = await page.$('body > div');
  return el.screenshot({ type: 'png' });
}

/** Build a multi-size .ico from a large PNG using Pillow's ICO sizes parameter. */
async function buildIco(sources, outPath, allSizes) {
  // Pillow ICO: pass the LARGEST image + sizes list; Pillow auto-resizes.
  const { execSync } = require('child_process');
  const tmpDir = path.join(PREVIEW, '_ico_tmp');
  fs.mkdirSync(tmpDir, { recursive: true });
  // Use the largest rendered PNG as the master
  const largest = sources[sources.length - 1];
  const masterPath = path.join(tmpDir, 'master.png');
  fs.writeFileSync(masterPath, largest.pngBuffer);
  const cfgPath = path.join(tmpDir, 'ico_config.json');
  fs.writeFileSync(cfgPath, JSON.stringify({
    master_png: masterPath,
    out_path: outPath,
    sizes: allSizes,
  }));
  const pyPath = path.join(tmpDir, 'build_ico.py');
  fs.writeFileSync(pyPath, [
    'import json, sys',
    'from PIL import Image',
    'cfg = json.load(open(sys.argv[1], encoding="utf-8"))',
    'img = Image.open(cfg["master_png"]).convert("RGBA")',
    'img.save(cfg["out_path"], format="ICO", sizes=[tuple(s) for s in cfg["sizes"]])',
    'print("ICO written:", cfg["out_path"])',
  ].join('\n'));
  execSync(`venv\\Scripts\\python.exe "${pyPath}" "${cfgPath}"`, {
    cwd: path.join(__dirname, '..', 'backend'), stdio: 'pipe',
  });
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setViewportSize({ width: 1024, height: 1024 });

  const results = [];
  function log(name, ok, detail) {
    results.push({ name, ok, detail });
    console.log(`  ${ok ? 'OK  ' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  }

  // ── 1. Render mark at 1024 for verification ──────────────────────────
  console.log('\n1. Rendering mark at 1024 for verification...');
  const mark1024 = await renderSvg(page, MARK_SVG, 1024);
  fs.writeFileSync(path.join(PREVIEW, 'mark-render-1024.png'), mark1024);
  log('Mark rendered at 1024', mark1024.length > 10000, `${mark1024.length} bytes`);

  // ── 2. PWA icons (transparent bg) ────────────────────────────────────
  console.log('\n2. PWA icons (transparent background)...');
  const pwaSizes = [72, 96, 120, 128, 144, 152, 167, 180, 192, 256, 384, 512];
  for (const size of pwaSizes) {
    const png = await renderSvg(page, MARK_SVG, size);
    const name = `icon-${size}x${size}.png`;
    fs.writeFileSync(path.join(ICONS, name), png);
    log(`  ${name}`, png.length > 500, `${png.length} bytes`);
    // Also write the alias name (icon-192.png etc.)
    if ([96, 192, 512].includes(size)) {
      fs.writeFileSync(path.join(ICONS, `icon-${size}.png`), png);
    }
  }

  // ── 3. Maskable icons (navy bg, 72% scale for safe zone) ─────────────
  console.log('\n3. Maskable icons (navy background, safe zone)...');
  for (const size of [192, 512]) {
    const png = await renderMaskable(page, size, NAVY, 0.72);
    const name = `icon-${size}-maskable.png`;
    fs.writeFileSync(path.join(ICONS, name), png);
    log(`  ${name}`, png.length > 5000, `${png.length} bytes`);
    // Also the maskable-icon alias
    fs.writeFileSync(path.join(ICONS, `maskable-icon-${size}x${size}.png`), png);
  }

  // ── 4. Apple touch icon (180, solid navy bg) ─────────────────────────
  console.log('\n4. Apple touch icon...');
  {
    const png = await renderMaskable(page, 180, NAVY, 0.72);
    fs.writeFileSync(path.join(ICONS, 'apple-touch-icon.png'), png);
    log('  apple-touch-icon.png', png.length > 3000, `${png.length} bytes`);
  }

  // ── 5. Favicon (multi-size ICO: 16/32/48) ───────────────────────────
  console.log('\n5. Favicon ICO (16/32/48)...');
  {
    const sizes = [16, 32, 48];
    const sources = [];
    for (const size of sizes) {
      const png = await renderSvg(page, MARK_SVG, size);
      sources.push({ size, pngBuffer: png });
    }
    await buildIco(sources, path.join(ICONS, 'favicon.ico'), sizes.map(s => [s, s]));
    const stat = fs.statSync(path.join(ICONS, 'favicon.ico'));
    log('  favicon.ico', stat.size > 1000, `${stat.size} bytes`);
  }

  // ── 6. Windows ICO (16-256) ──────────────────────────────────────────
  console.log('\n6. Windows ICO (16/24/32/48/64/128/256)...');
  {
    const sizes = [16, 24, 32, 48, 64, 128, 256];
    const sources = [];
    for (const size of sizes) {
      const png = await renderSvg(page, MARK_SVG, size);
      sources.push({ size, pngBuffer: png });
    }
    await buildIco(sources, path.join(BRAND, 'schemeknit-windows.ico'), sizes.map(s => [s, s]));
    const stat = fs.statSync(path.join(BRAND, 'schemeknit-windows.ico'));
    log('  schemeknit-windows.ico', stat.size > 5000, `${stat.size} bytes`);
  }

  // ── 7. Social / OG images ────────────────────────────────────────────
  console.log('\n7. Social / OG images...');
  {
    const social = await renderSocial(page, 1200, 630);
    fs.writeFileSync(path.join(ICONS, 'social-preview.png'), social);
    log('  social-preview.png', social.length > 20000, `${social.length} bytes`);
    fs.writeFileSync(path.join(ICONS, 'og-image.png'), social);
    log('  og-image.png', social.length > 20000, `${social.length} bytes`);
  }

  // ── 8. Wordmark render ───────────────────────────────────────────────
  console.log('\n8. Wordmark render...');
  {
    await page.setContent(`
      <html><body style="margin:0;padding:0;">
        <div style="width:1280px;height:230px;">${WORDMARK_SVG}</div>
      </body></html>
    `, { waitUntil: 'load' });
    const el = await page.$('div');
    const png = await el.screenshot({ type: 'png', omitBackground: true });
    fs.writeFileSync(path.join(PREVIEW, 'wordmark-render.png'), png);
    log('  wordmark-render.png', png.length > 5000, `${png.length} bytes`);
  }

  // ── Summary ──────────────────────────────────────────────────────────
  const failed = results.filter(r => !r.ok).length;
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Asset generation: ${results.length - failed} ok, ${failed} failed`);
  console.log(`${'='.repeat(60)}`);

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
})();
