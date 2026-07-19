"""Generate docs/images/nightforge-logo.png — matches the in-app sidebar wordmark."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "nightforge-logo.png"

ACCENT = (232, 163, 60)  # --app-accent
ACCENT_INK = (236, 184, 101)  # --app-accent-ink (dark theme)
INK = (240, 240, 242)
BOX_BG = (26, 26, 31)
BOX_BORDER = (46, 46, 54)

FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT_ITALIC = "C:/Windows/Fonts/segoeuiz.ttf"


def draw_moon_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    """Lucide moon-star — filled crescent + sparkle, matches sidebar at 16px."""
    r = 7.2
    # Crescent via two overlapping circles (same technique as Lucide fill path)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    draw.ellipse([cx - r + 4.5, cy - r - 0.5, cx + r + 4.5, cy + r - 0.5], fill=BOX_BG)
    # Sparkle (top-right)
    sx, sy = cx + 5.5, cy - 6.5
    draw.line([(sx, sy - 2.5), (sx, sy + 2.5)], fill=color, width=2)
    draw.line([(sx - 2.5, sy), (sx + 2.5, sy)], fill=color, width=2)


def main() -> None:
    font_night = ImageFont.truetype(FONT_BOLD, 21)
    font_forge = ImageFont.truetype(FONT_ITALIC, 21)

    probe = Image.new("RGBA", (1, 1))
    pd = ImageDraw.Draw(probe)
    night_w = pd.textlength("Night", font=font_night)
    forge_w = pd.textlength("Forge", font=font_forge)
    width = int(50 + night_w + forge_w + 8)
    height = 48

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 4, 40, 44], radius=10, fill=BOX_BG, outline=BOX_BORDER, width=1)
    draw_moon_star(draw, 20, 24, ACCENT)

    draw.text((50, 11), "Night", font=font_night, fill=INK)
    draw.text((50 + night_w, 11), "Forge", font=font_forge, fill=ACCENT_INK)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"Wrote {OUT} ({width}×{height})")


if __name__ == "__main__":
    main()
