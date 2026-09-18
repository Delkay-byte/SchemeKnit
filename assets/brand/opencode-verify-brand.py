"""
Comprehensive brand asset verification.
Checks every generated asset: dimensions, alpha/background, brand colors present,
no old green branding, no old navy #042758 gradient.
"""
import os, sys, json
from collections import Counter
from PIL import Image

ICONS = r"C:\Users\SAVIOUR\Documents\TeachFlow\frontend\public\icons"
BRAND = r"C:\Users\SAVIOUR\Documents\TeachFlow\assets\brand"

NAVY = (0x10, 0x2A, 0x43)
CYAN = (0x04, 0xA9, 0xCE)
OLD_NAVY = (0x04, 0x27, 0x58)  # old brand navy
OLD_GREEN = (0x16, 0xAE, 0x74) # old brand green

def color_dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

def check_png(path, expect_transparent, expect_navy, expect_cyan, check_no_green=True):
    img = Image.open(path)
    rgba = img.convert("RGBA")
    w, h = rgba.size
    pixels = list(rgba.getdata())
    opaque = [p for p in pixels if p[3] > 128]

    issues = []
    if expect_transparent:
        transp = sum(1 for p in pixels if p[3] <= 128)
        if transp == 0:
            issues.append("expected transparent bg but fully opaque")

    # Brand color check
    has_navy = has_cyan = has_old_green = has_old_navy = False
    if opaque:
        for p in opaque:
            r, g, b = p[0], p[1], p[2]
            if not has_navy and color_dist((r, g, b), NAVY) < 50:
                has_navy = True
            if not has_cyan and color_dist((r, g, b), CYAN) < 50:
                has_cyan = True
            if not has_old_green and color_dist((r, g, b), OLD_GREEN) < 50:
                has_old_green = True
            if not has_old_navy and color_dist((r, g, b), OLD_NAVY) < 50:
                has_old_navy = True
    else:
        issues.append("no opaque pixels at all")

    if expect_navy and not has_navy:
        issues.append("navy #102A43 not found")
    if expect_cyan and not has_cyan:
        issues.append("cyan #04A9CE not found")
    if check_no_green and has_old_green:
        issues.append("OLD GREEN #16AE74 found (old branding!)")
    if has_old_navy and not has_navy:
        issues.append("OLD NAVY #042758 found without new navy")

    return {
        "path": os.path.basename(path),
        "size": f"{w}x{h}",
        "mode": rgba.mode,
        "opaque_pct": f"{100*len(opaque)/len(pixels):.1f}%",
        "navy": has_navy,
        "cyan": has_cyan,
        "old_green": has_old_green,
        "issues": issues,
    }

# ── Verify all PNG assets ────────────────────────────────────────────────
checks = []

# Transparent icons (mark only) — expect navy + cyan, transparent bg
transparent_icons = [
    "icon-72x72.png", "icon-96x96.png", "icon-120x120.png", "icon-128x128.png",
    "icon-144x144.png", "icon-152x152.png", "icon-167x167.png", "icon-180x180.png",
    "icon-192x192.png", "icon-256x256.png", "icon-384x384.png", "icon-512x512.png",
    "icon-96.png", "icon-192.png", "icon-512.png",
    "social-preview.png", "og-image.png",
]
for name in transparent_icons:
    p = os.path.join(ICONS, name)
    if os.path.exists(p):
        # social/og have navy bg so not transparent
        is_social = "social" in name or "og-image" in name
        checks.append(check_png(p, expect_transparent=not is_social,
                                expect_navy=True, expect_cyan=True))

# Maskable / apple touch (solid navy bg) — expect navy bg, cyan mark
for name in ["icon-192-maskable.png", "icon-512-maskable.png",
             "maskable-icon-192x192.png", "maskable-icon-512x512.png",
             "apple-touch-icon.png"]:
    p = os.path.join(ICONS, name)
    if os.path.exists(p):
        checks.append(check_png(p, expect_transparent=False,
                                expect_navy=True, expect_cyan=True))

# ── Report ────────────────────────────────────────────────────────────────
print(f"\n{'='*90}")
print(f"BRAND ASSET VERIFICATION — {len(checks)} PNG assets")
print(f"{'='*90}")
all_ok = True
for c in checks:
    status = "PASS" if not c["issues"] else "FAIL"
    if c["issues"]:
        all_ok = False
    print(f"  {status}  {c['path']:32s} {c['size']:10s} opaque={c['opaque_pct']:>6s} "
          f"navy={'Y' if c['navy'] else 'N'} cyan={'Y' if c['cyan'] else 'N'} "
          f"oldgreen={'Y' if c['old_green'] else 'N'}")
    for issue in c["issues"]:
        print(f"         ! {issue}")

# ── ICO verification ─────────────────────────────────────────────────────
print(f"\n{'='*90}")
print("ICO VERIFICATION")
print(f"{'='*90}")
for ico, expected_sizes in [
    (os.path.join(ICONS, "favicon.ico"), {(16,16),(32,32),(48,48)}),
    (os.path.join(BRAND, "schemeknit-windows.ico"),
     {(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)}),
]:
    try:
        img = Image.open(ico)
        actual = img.ico.sizes() if hasattr(img, "ico") and hasattr(img.ico, "sizes") else set()
        ok = actual == expected_sizes
        if not ok:
            all_ok = False
        print(f"  {'PASS' if ok else 'FAIL'}  {os.path.basename(ico):32s} "
              f"sizes={sorted(actual)}")
        if not ok:
            print(f"         ! expected {sorted(expected_sizes)}")
    except Exception as e:
        all_ok = False
        print(f"  FAIL  {os.path.basename(ico)} — {e}")

# ── SVG verification ─────────────────────────────────────────────────────
print(f"\n{'='*90}")
print("SVG VERIFICATION")
print(f"{'='*90}")
for svg_name in ["schemeknit-mark.svg", "schemeknit-wordmark.svg"]:
    p = os.path.join(BRAND, svg_name)
    content = open(p, encoding="utf-8").read()
    issues = []
    if "base64" in content.lower():
        issues.append("contains base64 embedding (forbidden)")
    if ".png" in content or ".jpg" in content:
        issues.append("references raster image (forbidden)")
    if "#16ae74" in content.lower() or "#16AE74" in content:
        issues.append("old green #16AE74 found")
    if "#042758" in content:
        issues.append("old navy #042758 found")
    if "gradient" in content.lower():
        issues.append("uses gradient (old brand treatment)")
    has_navy = "#102A43" in content
    has_cyan = "#04A9CE" in content
    if not has_navy:
        issues.append("navy #102A43 not found")
    if not has_cyan:
        issues.append("cyan #04A9CE not found")
    has_viewbox = "viewBox" in content
    if not has_viewbox:
        issues.append("no viewBox")
    ok = not issues
    if not ok:
        all_ok = False
    print(f"  {'PASS' if ok else 'FAIL'}  {svg_name:32s} "
          f"navy={'Y' if has_navy else 'N'} cyan={'Y' if has_cyan else 'N'} "
          f"size={len(content)}b")
    for issue in issues:
        print(f"         ! {issue}")

# ── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'='*90}")
print(f"OVERALL: {'ALL PASS' if all_ok else 'FAILURES PRESENT'}")
print(f"{'='*90}")
sys.exit(0 if all_ok else 1)
