"""Verify ICO files contain all expected sizes."""
import sys
from PIL import Image

for ico_path in [
    r"C:\Users\SAVIOUR\Documents\TeachFlow\frontend\public\icons\favicon.ico",
    r"C:\Users\SAVIOUR\Documents\TeachFlow\assets\brand\schemeknit-windows.ico",
]:
    print(f"\n=== {ico_path}")
    try:
        img = Image.open(ico_path)
        print(f"  format: {img.format}")
        print(f"  size: {img.size}")
        print(f"  mode: {img.mode}")
        # List all frames/sizes in the ICO
        try:
            for i, frame in enumerate(getattr(img, "apng", []) or []):
                print(f"  frame {i}: {frame.size}")
        except Exception:
            pass
        # ICO specific
        if hasattr(img, "ico"):
            entries = img.ico.sizes() if hasattr(img.ico, 'sizes') else 'n/a'
            print(f"  ICO sizes: {entries}")
        # Re-open to check all sizes
        img2 = Image.open(ico_path)
        sizes = []
        while True:
            try:
                sizes.append(img2.size)
                img2.seek(img2.tell() + 1)
            except EOFError:
                break
        print(f"  all contained sizes: {sizes}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Check apple-touch-icon
at = Image.open(r"C:\Users\SAVIOUR\Documents\TeachFlow\frontend\public\icons\apple-touch-icon.png")
print(f"\napple-touch-icon.png: {at.size} {at.mode}")
