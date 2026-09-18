"""Render the SchemeKnit SVG mark + wordmark to PNG for visual comparison against the reference."""
import subprocess
import sys
import os

# Check if cairosvg or rsvg-convert is available
def find_renderer():
    try:
        import cairosvg
        return "cairosvg"
    except ImportError:
        pass
    try:
        subprocess.run(["rsvg-convert", "--version"], capture_output=True, check=True)
        return "rsvg"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        subprocess.run(["inkscape", "--version"], capture_output=True, check=True)
        return "inkscape"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    # Check for ImageMagick
    try:
        subprocess.run(["magick", "-version"], capture_output=True, check=True)
        return "magick"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return None

renderer = find_renderer()
print(f"Renderer: {renderer}")

brand_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "brand")
out_dir = os.path.join(os.path.dirname(__file__), "_brand_preview")
os.makedirs(out_dir, exist_ok=True)

if renderer == "cairosvg":
    import cairosvg
    cairosvg.svg2png(
        url=os.path.join(brand_dir, "schemeknit-mark.svg"),
        write_to=os.path.join(out_dir, "mark-preview.png"),
        output_width=512, output_height=512,
    )
    cairosvg.svg2png(
        url=os.path.join(brand_dir, "schemeknit-wordmark.svg"),
        write_to=os.path.join(out_dir, "wordmark-preview.png"),
        output_width=1200, output_height=220,
    )
    print("Rendered with cairosvg")
elif renderer == "rsvg":
    subprocess.run(["rsvg-convert", "-w", "512", "-h", "512",
                    "-o", os.path.join(out_dir, "mark-preview.png"),
                    os.path.join(brand_dir, "schemeknit-mark.svg")], check=True)
    subprocess.run(["rsvg-convert", "-w", "1200", "-h", "220",
                    "-o", os.path.join(out_dir, "wordmark-preview.png"),
                    os.path.join(brand_dir, "schemeknit-wordmark.svg")], check=True)
    print("Rendered with rsvg-convert")
elif renderer == "magick":
    subprocess.run(["magick", "-background", "none", "-density", "300",
                    os.path.join(brand_dir, "schemeknit-mark.svg"),
                    "-resize", "512x512",
                    os.path.join(out_dir, "mark-preview.png")], check=True)
    subprocess.run(["magick", "-background", "none", "-density", "300",
                    os.path.join(brand_dir, "schemeknit-wordmark.svg"),
                    "-resize", "1200x220",
                    os.path.join(out_dir, "wordmark-preview.png")], check=True)
    print("Rendered with ImageMagick")
else:
    print("No SVG renderer found! Install cairosvg: pip install cairosvg")
    sys.exit(1)

# Also copy the reference for side-by-side
import shutil
shutil.copy(os.path.join(brand_dir, "schemeknit-reference.png"),
            os.path.join(out_dir, "reference.png"))
print(f"Preview files in {out_dir}")
