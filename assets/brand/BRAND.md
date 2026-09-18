# SchemeKnit Brand Assets

## Approved Mark — Interlocking-S

The approved SchemeKnit brand mark is the **interlocking-S symbol** rendered in
two solid colors:

| Role | Color | Hex | Usage |
|---|---|---|---|
| **Primary navy** | `#102A43` | Mark body, wordmark "Scheme", theme color, headers |
| **Accent cyan** | `#04A9CE` | Mark accent strokes, wordmark "Knit", highlights |

The mark has **180° rotational symmetry** — the two interlocking strokes form
an S that reads the same upside down.

### Source of truth

- **Vector master:** `schemeknit-mark.svg` — real bezier geometry (no embedded raster)
- **Wordmark:** `schemeknit-wordmark.svg` — "Scheme" in navy, "Knit" in cyan
- **Approved source:** The interlocking-S design supplied by the brand owner

### Cropping

The vector master is **tightly cropped**: the mark occupies 93% of the viewBox
width and 86% of the viewBox height (the mark is slightly wider than tall).
The white margins from the original 1024×1024 source have been removed.

## Files

### Vector (source of truth)

| File | Contents |
|---|---|
| `schemeknit-mark.svg` | Interlocking-S mark, transparent bg, tight crop |
| `schemeknit-wordmark.svg` | "SchemeKnit" wordmark, Scheme=navy, Knit=cyan |

### Raster derivatives (all generated from the vector master)

| File | Sizes | Purpose |
|---|---|---|
| `frontend/public/icons/favicon.ico` | 16/32/48 | Browser tab icon |
| `frontend/public/icons/icon-*.png` | 72–512 | PWA icons, transparent bg |
| `frontend/public/icons/icon-*-maskable.png` | 192/512 | Maskable PWA icons, navy bg |
| `frontend/public/icons/apple-touch-icon.png` | 180 | iOS home screen |
| `frontend/public/icons/social-preview.png` | 1200×630 | Social sharing |
| `frontend/public/icons/og-image.png` | 1200×630 | Open Graph |
| `schemeknit-windows.ico` | 16–256 | Windows application icon |

### Brand color tokens

Brand colors are centralized as CSS custom properties in
`frontend/src/app/globals.css`:

```css
--brand-navy: 209 61% 16%;   /* #102A43 */
--brand-cyan: 191 96% 41%;   /* #04A9CE */
```

And exposed as Tailwind utilities in `frontend/tailwind.config.js`:

```
bg-brand-navy  text-brand-navy  border-brand-navy
bg-brand-cyan  text-brand-cyan  border-brand-cyan
```

**Important:** These are brand colors only. Semantic status colors
(green=success, red=error, amber=warning) are separate and must not be
replaced by brand colors.

## Regeneration

All raster assets are generated from the vector masters:

```bash
cd frontend
node opencode-generate-assets.js     # renders SVG → PNG/ICO via Playwright
```

Verification:

```bash
cd backend
venv\Scripts\python.exe ..\assets\brand\opencode-verify-brand.py
```

This checks every asset for: correct dimensions, alpha/background, navy+cyan
presence, and absence of old-brand green (#16AE74) or old navy (#042758).
