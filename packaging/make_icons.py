"""Render the app icon (static/img/mark.svg redrawn with Pillow) as PNG sizes,
plus ``icon.ico`` (Windows) and, on macOS, ``icon.icns`` via ``iconutil``.

Usage: python packaging/make_icons.py <out_dir>
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def render(size: int) -> Image.Image:
    s = 8  # supersample for smooth edges
    n = size * s
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = n / 40.0  # mark.svg viewBox is 40x40

    def circle(cx, cy, r, **kw):
        d.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], **kw)

    circle(20, 20, 19, fill=(11, 17, 24, 255), outline=(47, 58, 71, 255), width=max(1, int(0.8 * u)))
    circle(20, 20, 14.2, outline=(18, 180, 216, 255), width=int(2.6 * u))
    circle(20, 20, 10.6, fill=(9, 38, 58, 255))
    pts = [(11.6, 21), (15, 21), (16.5, 17.4), (18.9, 24.8), (21.1, 18.2), (22.5, 21), (28.4, 21)]
    d.line([(x * u, y * u) for x, y in pts], fill=(110, 224, 250, 255),
           width=int(1.6 * u), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    pngs = {}
    for size in SIZES:
        p = out / f"icon_{size}.png"
        render(size).save(p)
        pngs[size] = p
    # Windows .ico
    render(256).save(out / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    # macOS .icns
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = out / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for base in (16, 32, 128, 256, 512):
            shutil.copy(pngs[base], iconset / f"icon_{base}x{base}.png")
            shutil.copy(pngs[base * 2], iconset / f"icon_{base}x{base}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out / "icon.icns")], check=True)
    print("icons written to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "packaging/build-icons"))
