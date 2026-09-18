"""Analyze the two candidate logo images from Downloads."""
from collections import Counter
from PIL import Image

candidates = [
    (r"C:\Users\SAVIOUR\Downloads\image.png", "FIRST (image.png)"),
    (r"C:\Users\SAVIOUR\Downloads\image (1).png", "SECOND (image (1).png)"),
]

TARGET_NAVY = (0x10, 0x2A, 0x43)
TARGET_CYAN = (0x04, 0xA9, 0xCE)

def color_dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

for path, label in candidates:
    img = Image.open(path)
    print(f"\n{'='*70}")
    print(f"{label}")
    print(f"  size: {img.size}  mode: {img.mode}")
    rgba = img.convert("RGBA")
    pixels = list(rgba.getdata())
    total = len(pixels)
    opaque = [p for p in pixels if p[3] > 128]
    transp = total - len(opaque)
    print(f"  transparent: {transp} ({100*transp/total:.1f}%)  opaque: {len(opaque)}")

    cnt = Counter((p[0], p[1], p[2]) for p in opaque)
    print(f"  top 12 colors (opaque):")
    navy_found = cyan_found = False
    for color, count in cnt.most_common(12):
        pct = 100 * count / len(opaque)
        hexc = "#{:02X}{:02X}{:02X}".format(*color)
        dn = color_dist(color, TARGET_NAVY)
        dc = color_dist(color, TARGET_CYAN)
        tag = ""
        if dn < 50: tag += " [~NAVY #102A43]"; navy_found = True
        if dc < 50: tag += " [~CYAN #04A9CE]"; cyan_found = True
        print(f"    {hexc}  {pct:5.1f}%  dist_navy={dn:5.0f} dist_cyan={dc:5.0f}{tag}")
    print(f"  NAVY #102A43 present: {navy_found}")
    print(f"  CYAN #04A9CE present: {cyan_found}")

    bbox = rgba.getbbox()
    print(f"  content bbox: {bbox}")
    if bbox:
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        print(f"  content size: {bw}x{bh} on canvas {img.size[0]}x{img.size[1]}")
        print(f"  fill ratio: {bw*100/img.size[0]:.0f}% x {bh*100/img.size[1]:.0f}%")
        # margins
        l, t = bbox[0], bbox[1]
        r, b = img.size[0] - bbox[2], img.size[1] - bbox[3]
        print(f"  margins: L={l} T={t} R={r} B={b}")
    # Check for any green (old brand)
    green_pixels = sum(1 for p in opaque if p[1] > 100 and p[1] > p[0] + 30 and p[1] > p[2] + 30)
    print(f"  green-ish pixels: {green_pixels} ({100*green_pixels/len(opaque):.1f}%)")
