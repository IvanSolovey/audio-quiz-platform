"""
Generate PWA icons and OG image for OSD Academy.
Run from project root: python scripts/generate_icons.py
"""
import os
import shutil
from pathlib import Path

os.makedirs("static", exist_ok=True)

# Bundled font — committed to the repo at static/fonts/InterTight-Bold.ttf.
# Falls back to common system font paths if for some reason the file is missing.
_REPO_FONT = Path("static/fonts/InterTight-Bold.ttf")

_SYSTEM_FONT_FALLBACKS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int):
    """Return an ImageFont, preferring the bundled repo font."""
    from PIL import ImageFont

    candidates = [str(_REPO_FONT)] + _SYSTEM_FONT_FALLBACKS
    for path in candidates:
        try:
            return ImageFont.truetype(path, max(size, 8))
        except (OSError, IOError):
            continue
    # Last-resort: Pillow built-in bitmap font
    try:
        return ImageFont.load_default(size=max(size, 8))
    except TypeError:
        return ImageFont.load_default()


# ─── Icons ────────────────────────────────────────────────────────────────────

def create_icon(size):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded rectangle background (#1A3A5C)
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=size // 6,
        fill="#1A3A5C",
    )

    # "OSD" text in accent orange
    font = _load_font(max(size // 3, 6))
    text = "OSD"
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) // 2 - bbox[0]
        y = (size - text_h) // 2 - bbox[1]
    except Exception:
        x = size // 4
        y = size // 3
    draw.text((x, y), text, fill="#F4871F", font=font)

    return img


try:
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401 — import check

    for size in [16, 32, 180, 192, 512]:
        img = create_icon(size)
        img.save(f"static/icon-{size}x{size}.png")
        print(f"  icon-{size}x{size}.png")

    shutil.copy("static/icon-32x32.png", "static/favicon-32x32.png")
    shutil.copy("static/icon-16x16.png", "static/favicon-16x16.png")
    shutil.copy("static/icon-180x180.png", "static/apple-touch-icon.png")
    shutil.copy("static/icon-32x32.png", "static/favicon.ico")
    print("✅ Icons generated")

except ImportError:
    print("❌ Pillow not installed — run: pip install Pillow")
    raise

# ─── OG Image ─────────────────────────────────────────────────────────────────

def create_og_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1200, 630), "#1A3A5C")
    draw = ImageDraw.Draw(img)

    # Accent stripe
    draw.rectangle([0, 0, 8, 630], fill="#F4871F")

    font_large = _load_font(80)
    font_small = _load_font(36)

    draw.text((80, 200), "OSD Academy", fill="white", font=font_large)
    draw.text((80, 320), "Навчальна платформа аутсорсингового відділу продажів", fill="#A0B8D0", font=font_small)
    draw.text((80, 380), "osd24.com", fill="#F4871F", font=font_small)

    img.save("static/og-image.png")
    print("✅ OG image created (static/og-image.png)")


create_og_image()
