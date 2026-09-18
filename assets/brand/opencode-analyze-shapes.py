"""Deep analysis of both logo candidates: shape structure, symmetry, region layout."""
import numpy as np
from PIL import Image

for path, label in [
    (r"C:\Users\SAVIOUR\Downloads\image.png", "FIRST (image.png) — navy+cyan"),
    (r"C:\Users\SAVIOUR\Downloads\image (1).png", "SECOND (image (1).png) — navy+green"),
]:
    img = Image.open(path).convert("RGB")
    a = np.array(img)
    h, w, _ = a.shape
    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"  canvas: {w}x{h}")

    # Non-white mask (the logo ink)
    nonwhite = (a.sum(axis=2) < 720)  # sum of RGB < 720 means not near-white
    print(f"  non-white pixels: {nonwhite.sum()} ({100*nonwhite.sum()/(h*w):.1f}%)")

    # Bounding box of ink
    rows = np.any(nonwhite, axis=1)
    cols = np.any(nonwhite, axis=0)
    rmin, rmax = np.argmax(rows), h - 1 - np.argmax(rows[::-1])
    cmin, cmax = np.argmax(cols), w - 1 - np.argmax(cols[::-1])
    print(f"  ink bbox: x[{cmin}..{cmax}] y[{rmin}..{rmax}]  size {cmax-cmin+1}x{rmax-rmin+1}")
    print(f"  margins: L={cmin} T={rmin} R={w-1-cmax} B={h-1-rmax}")

    # Color segmentation: navy vs accent (cyan or green)
    navy = (np.abs(a[:,:,0].astype(int) - 0x10) < 40) & \
           (np.abs(a[:,:,1].astype(int) - 0x2A) < 40) & \
           (np.abs(a[:,:,2].astype(int) - 0x43) < 40)
    # accent: high blue (cyan) or high green
    cyan = (a[:,:,2].astype(int) > 150) & (a[:,:,2] > a[:,:,0] + 40) & (a[:,:,1] > 100)
    green = (a[:,:,1].astype(int) > 120) & (a[:,:,1] > a[:,:,0] + 40) & (a[:,:,1] > a[:,:,2] + 40)
    print(f"  navy pixels: {navy.sum()} ({100*navy.sum()/(h*w):.1f}%)")
    print(f"  cyan-ish pixels: {cyan.sum()} ({100*cyan.sum()/(h*w):.1f}%)")
    print(f"  green-ish pixels: {green.sum()} ({100*green.sum()/(h*w):.1f}%)")

    # Vertical profile: ink density per row band (16 bands)
    print(f"  vertical ink profile (16 bands, % ink):")
    band = h // 16
    for i in range(16):
        y0, y1 = i * band, min((i + 1) * band, h)
        density = nonwhite[y0:y1].mean() * 100
        bar = "#" * int(density)
        print(f"    y {y0:4d}-{y1:4d}: {density:5.1f}% {bar}")

    # Horizontal profile
    print(f"  horizontal ink profile (16 bands, % ink):")
    bandw = w // 16
    for i in range(16):
        x0, x1 = i * bandw, min((i + 1) * bandw, w)
        density = nonwhite[:, x0:x1].mean() * 100
        bar = "#" * int(density)
        print(f"    x {x0:4d}-{x1:4d}: {density:5.1f}% {bar}")

    # Check diagonal symmetry (interlocking S often has 180-degree rotational symmetry)
    rotated = np.rot90(nonwhite, 2)
    symmetry = (nonwhite == rotated).mean() * 100
    print(f"  180-deg rotational symmetry: {symmetry:.1f}%")

    # Horizontal flip symmetry
    flipped = nonwhite[:, ::-1]
    hsym = (nonwhite == flipped).mean() * 100
    print(f"  horizontal flip symmetry: {hsym:.1f}%")

    # Where is the accent color located? (top vs bottom)
    accent = cyan if cyan.sum() > green.sum() else green
    if accent.sum() > 0:
        ar = np.any(accent, axis=1)
        ac = np.any(accent, axis=0)
        armin, armax = np.argmax(ar), h - 1 - np.argmax(ar[::-1])
        acmin, acmax = np.argmax(ac), w - 1 - np.argmax(ac[::-1])
        print(f"  accent region: x[{acmin}..{acmax}] y[{armin}..{armax}]")
        # Centroid
        ay, ax = np.nonzero(accent)
        print(f"  accent centroid: ({ax.mean():.0f}, {ay.mean():.0f}) — canvas center=({w//2},{h//2})")
    if navy.sum() > 0:
        ny, nx = np.nonzero(navy)
        print(f"  navy centroid: ({nx.mean():.0f}, {ny.mean():.0f}) — canvas center=({w//2},{h//2})")
