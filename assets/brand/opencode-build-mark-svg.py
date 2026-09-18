"""
Parse the approved SchemeKnit logo SVG (interlocking-S, navy #102A43 + cyan #04A9CE).
- Remove the white background path
- Evaluate all cubic bezier curves to find the exact ink bounding box
- Produce a tightly-cropped, centered SVG with transparent background
"""
import re, math

SRC = r"C:\Users\SAVIOUR\Downloads\schemeknit.svg"
OUT = r"C:\Users\SAVIOUR\Documents\TeachFlow\assets\brand\schemeknit-mark.svg"

with open(SRC, "r", encoding="utf-8") as f:
    raw = f.read()

# ── Extract all <path> elements ──────────────────────────────────────────
path_re = re.compile(r'<path\s+fill="([^"]*)"\s+d="([^"]*)"\s*/>')
paths = path_re.findall(raw)
print(f"Found {len(paths)} paths")
for fill, d in paths:
    print(f"  fill={fill:8s}  d_len={len(d)}")

# ── Parse path data: M, C, L, Z commands ──────────────────────────────────
def parse_path(d):
    """Return list of (cmd, coords) tuples."""
    tokens = re.findall(r'([MLCZ])\s*([^MLCZ]*)', d)
    return [(cmd, [float(x) for x in re.findall(r'-?[\d.]+', coords)])
            for cmd, coords in tokens]

def eval_cubic(p0, p1, p2, p3, t):
    mt = 1 - t
    x = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
    y = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
    return (x, y)

# ── Compute bounding box of all non-white paths ──────────────────────────
all_points = []
parsed = []
for fill, d in paths:
    if fill.lower() in ("white", "#ffffff"):
        print(f"  SKIPPING white background path")
        continue
    cmds = parse_path(d)
    parsed.append((fill, cmds))
    # Walk the commands, tracking current point
    cur = None
    sub_start = None
    for cmd, coords in cmds:
        if cmd == "M":
            cur = (coords[0], coords[1])
            sub_start = cur
            all_points.append(cur)
        elif cmd == "L":
            cur = (coords[0], coords[1])
            all_points.append(cur)
        elif cmd == "C":
            # C x1 y1 x2 y2 x y
            p1 = (coords[0], coords[1])
            p2 = (coords[2], coords[3])
            p3 = (coords[4], coords[5])
            # Sample the bezier densely for exact bbox
            for i in range(1, 65):
                t = i / 64.0
                all_points.append(eval_cubic(cur, p1, p2, p3, t))
            cur = p3
        elif cmd == "Z":
            if sub_start:
                all_points.append(sub_start)
                cur = sub_start

xs = [p[0] for p in all_points]
ys = [p[1] for p in all_points]
x0, x1 = min(xs), max(xs)
y0, y1 = min(ys), max(ys)
print(f"\nExact ink bounding box:")
print(f"  x: {x0:.2f} .. {x1:.2f}  (width {x1-x0:.2f})")
print(f"  y: {y0:.2f} .. {y1:.2f}  (height {y1-y0:.2f})")
print(f"  on canvas 1024x1024")
print(f"  margins: L={x0:.0f} T={y0:.0f} R={1024-x1:.0f} B={1024-y1:.0f}")
print(f"  fill ratio: {100*(x1-x0)/1024:.0f}% x {100*(y1-y0)/1024:.0f}%")

# ── Build clean SVG: tight crop + small margin, centered ─────────────────
# Add 4% padding around the mark for visual breathing room
W = x1 - x0
H = y1 - y0
pad = max(W, H) * 0.04
cx = (x0 + x1) / 2
cy = (y0 + y1) / 2

# New viewBox: square, centered on the mark, with padding
half = max(W, H) / 2 + pad
vb_x = cx - half
vb_y = cy - half
vb_size = 2 * half
# Round to clean numbers
vb_x = round(vb_x, 1)
vb_y = round(vb_y, 1)
vb_size = round(vb_size, 1)

print(f"\nNew viewBox: {vb_x} {vb_y} {vb_size} {vb_size}")
print(f"  mark occupies {100*W/vb_size:.0f}% x {100*H/vb_size:.0f}% of viewBox")

# ── Write the clean SVG ──────────────────────────────────────────────────
svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x} {vb_y} {vb_size} {vb_size}" role="img" aria-label="SchemeKnit mark">\n'
svg += f'  <title>SchemeKnit</title>\n'
for fill, cmds in parsed:
    d_parts = []
    for cmd, coords in cmds:
        if cmd == "M":
            d_parts.append(f"M {coords[0]:.3f} {coords[1]:.3f}")
        elif cmd == "C":
            d_parts.append(f"C {coords[0]:.3f} {coords[1]:.3f} {coords[2]:.3f} {coords[3]:.3f} {coords[4]:.3f} {coords[5]:.3f}")
        elif cmd == "L":
            d_parts.append(f"L {coords[0]:.3f} {coords[1]:.3f}")
        elif cmd == "Z":
            d_parts.append("Z")
    svg += f'  <path fill="{fill}" d="{" ".join(d_parts)}"/>\n'
svg += '</svg>\n'

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(svg)
print(f"\nWrote: {OUT}")
print(f"  Size: {len(svg)} bytes")
print(f"  White background removed: yes")
print(f"  Transparent: yes (no background rect)")
