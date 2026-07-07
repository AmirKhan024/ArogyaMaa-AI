"""
Generate the ArogyaMaa ASHA PWA icon set.

Build-time tool only — NOT a runtime dependency. It renders the shipped PNG icons
(committed under ``app/static/icons/``) from code using Pillow, which is already installed
(no cairo/rsvg/ImageMagick required). Re-run whenever the brand mark changes:

    python scripts/gen_icons.py

Design: a rounded tile with a diagonal fuji-blue -> sakura-pink gradient (matching the ASHA
dashboard ``.page-header``), overlaid with a white lotus (an Indian maternal-wellness motif)
cradling a heart. The maskable and apple-touch variants are full-bleed squares with the mark
inside the safe zone so platform masking never clips it.
"""
import os

from PIL import Image, ImageChops, ImageDraw

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "static", "icons")

# Brand palette (from app/static/css/admin.css)
FUJI_700 = (30, 58, 95)     # #1e3a5f  deep blue
MID_PURPLE = (61, 43, 74)   # #3d2b4a  blend stop
SAKURA_600 = (219, 39, 119)  # #db2777  pink
WHITE = (255, 255, 255)

RENDER = 1024  # supersample, then downscale with LANCZOS for crisp edges


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient_stops(t):
    """Three-stop diagonal gradient: fuji -> mid purple -> sakura."""
    if t < 0.5:
        return _lerp(FUJI_700, MID_PURPLE, t / 0.5)
    return _lerp(MID_PURPLE, SAKURA_600, (t - 0.5) / 0.5)


def _gradient_tile(size):
    """Full-bleed diagonal gradient square (RGBA)."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    denom = (size - 1) * 2 or 1
    for y in range(size):
        for x in range(size):
            px[x, y] = _gradient_stops((x + y) / denom)
    return img.convert("RGBA")


def _heart_mask(box):
    """Return an 'L' mask of a rounded heart filling the given (w, h) box."""
    w, h = box
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    r = w * 0.26                       # radius of each top lobe
    lobe_y = h * 0.02
    d.ellipse([w * 0.5 - 2 * r, lobe_y, w * 0.5, lobe_y + 2 * r], fill=255)   # left lobe
    d.ellipse([w * 0.5, lobe_y, w * 0.5 + 2 * r, lobe_y + 2 * r], fill=255)   # right lobe
    # Lower body: a smooth wedge down to the point.
    d.polygon(
        [(w * 0.5 - 2 * r + 1, lobe_y + r),
         (w * 0.5 + 2 * r - 1, lobe_y + r),
         (w * 0.5, h * 0.98)],
        fill=255,
    )
    d.ellipse([w * 0.5 - 2 * r, lobe_y + r * 0.4, w * 0.5, lobe_y + r * 2.4], fill=255)
    d.ellipse([w * 0.5, lobe_y + r * 0.4, w * 0.5 + 2 * r, lobe_y + r * 2.4], fill=255)
    return m


def _pulse_mask(box, stroke):
    """Return an 'L' mask of an ECG heartbeat polyline across the given (w, h) box."""
    w, h = box
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    midy = h * 0.52
    pts = [
        (w * 0.10, midy), (w * 0.34, midy), (w * 0.42, midy * 0.72),
        (w * 0.50, midy * 1.55), (w * 0.58, midy * 0.30),
        (w * 0.66, midy), (w * 0.90, midy),
    ]
    d.line(pts, fill=255, width=stroke, joint="curve")
    return m


def _mark(canvas, scale):
    """Draw a white heart with a knocked-out ECG pulse line, centered on an RGBA canvas."""
    size = canvas.size[0]
    hw = int(size * 0.56 * scale)
    hh = int(size * 0.52 * scale)

    heart = Image.new("RGBA", (hw, hh), (0, 0, 0, 0))
    alpha = _heart_mask((hw, hh))
    # Knock the pulse line out of the heart so the gradient shows through.
    pulse = _pulse_mask((hw, hh), max(4, int(size * 0.028 * scale)))
    alpha = ImageChops.subtract(alpha, pulse)
    heart.putalpha(alpha)
    white = Image.new("RGBA", (hw, hh), (255, 255, 255, 255))
    white.putalpha(alpha)

    x = int((size - hw) / 2)
    y = int(size * 0.50 - hh / 2)
    canvas.alpha_composite(white, (x, y))
    return canvas


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def render(rounded=True, mark_scale=1.0):
    tile = _gradient_tile(RENDER)
    _mark(tile, mark_scale)
    if rounded:
        tile.putalpha(_rounded_mask(RENDER, int(RENDER * 0.22)))
    return tile


def save(img, name, size):
    out = img.resize((size, size), Image.LANCZOS)
    out.save(os.path.join(OUT_DIR, name))
    print("wrote", name, f"{size}x{size}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rounded = render(rounded=True, mark_scale=1.0)
    save(rounded, "icon-192.png", 192)
    save(rounded, "icon-512.png", 512)
    # Maskable + apple-touch: full-bleed square, mark inside ~80% safe zone.
    fullbleed = render(rounded=False, mark_scale=0.78)
    save(fullbleed, "icon-maskable-512.png", 512)
    save(fullbleed, "apple-touch-icon.png", 180)
    save(rounded, "favicon-32.png", 32)


if __name__ == "__main__":
    main()
