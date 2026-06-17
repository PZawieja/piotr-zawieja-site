#!/usr/bin/env python3
"""One-off generator for og-default.png — the social-preview card.

Run manually after branding changes:
    python scripts/generate_og.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
OUT = ROOT / "og-default.png"

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
SANS = FONT_DIR / "Arial.ttf"
SANS_BOLD = FONT_DIR / "Arial Bold.ttf"
MONO = FONT_DIR / "Courier New.ttf"
MONO_BOLD = FONT_DIR / "Courier New Bold.ttf"

BG = "#0d0d0f"
PANEL = "#131311"
BORDER = "#2a2924"
GOLD = "#c8a96e"
WHITE = "#f0ece4"
MUTED = "#8a8680"
DIM = "#5a5650"
GREEN = "#7a9e7e"

W, H = 1200, 630


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def draw_logo_mark(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    s = scale
    draw.rounded_rectangle([x, y, x + 32 * s, y + 32 * s], radius=7 * s, fill=PANEL, outline=BORDER)
    draw.rounded_rectangle([x + 5 * s, y + 8 * s, x + 27 * s, y + 13 * s], radius=2.5 * s, fill=GOLD)
    draw.rounded_rectangle([x + 5 * s, y + 15 * s, x + 20 * s, y + 20 * s], radius=2.5 * s, fill="#c8a96ecc")
    draw.rounded_rectangle([x + 5 * s, y + 22 * s, x + 14 * s, y + 27 * s], radius=2.5 * s, fill="#c8a96e99")


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, 4, H], fill=GOLD)

    draw_logo_mark(draw, 60, 56, scale=1.3)
    draw.text((108, 60), "goldlayer.dev", font=font(MONO_BOLD, 22), fill=GOLD)

    draw.text((58, 150), "Piotr Zawieja", font=font(SANS_BOLD, 72), fill=WHITE)
    draw.text((60, 232), "Analytics Engineer", font=font(SANS, 30), fill=MUTED)

    draw.line([(60, 296), (660, 296)], fill=BORDER, width=1)

    draw.text((60, 330), "dbt · Snowflake · AI-assisted analytics", font=font(SANS, 24), fill="#c8c4bc")
    draw.text((60, 372), "Revenue data · B2B SaaS · Berlin & Poland & remote", font=font(SANS, 19), fill=DIM)

    draw.rounded_rectangle([60, 440, 240, 480], radius=4, outline=GOLD, width=1)
    draw.text((150, 451), "WRITING", font=font(SANS, 15), fill=GOLD, anchor="mm")
    draw.rounded_rectangle([258, 440, 458, 480], radius=4, outline=BORDER, width=1)
    draw.text((358, 451), "OPEN SOURCE", font=font(SANS, 15), fill=DIM, anchor="mm")

    panel1 = (820, 160, 1120, 320)
    draw.rounded_rectangle(panel1, radius=4, fill=PANEL, outline=BORDER)
    draw.text((840, 178), "// mart layer", font=font(MONO, 13), fill=DIM)
    draw.text((840, 202), "SELECT", font=font(MONO_BOLD, 14), fill=GOLD)
    draw.text((860, 224), "customer_id, mrr,", font=font(MONO, 14), fill="#c8c4bc")
    draw.text((860, 246), "health_score", font=font(MONO, 14), fill="#c8c4bc")
    draw.text((840, 270), "FROM ", font=font(MONO_BOLD, 14), fill=GOLD)
    draw.text((885, 270), "gold_layer", font=font(MONO, 14), fill=GREEN)

    panel2 = (820, 360, 1120, 480)
    draw.rounded_rectangle(panel2, radius=4, fill=PANEL, outline=BORDER)
    draw.text((840, 378), "// anomaly signal", font=font(MONO, 13), fill=DIM)
    draw.text((840, 402), "z_score: ", font=font(MONO, 14), fill="#c8c4bc")
    draw.text((935, 402), "-3.2", font=font(MONO, 14), fill=GOLD)
    draw.text((840, 424), "flag: ", font=font(MONO, 14), fill="#c8c4bc")
    draw.text((905, 424), "true", font=font(MONO, 14), fill="#c0614a")
    draw.text((840, 446), "alert: ", font=font(MONO, 14), fill="#c8c4bc")
    draw.text((915, 446), '"MRR drop"', font=font(MONO, 14), fill=GREEN)

    draw.text((60, 575), "Analytics Engineering · Revenue Intelligence · AI-Ready Data",
              font=font(SANS, 15), fill="#3a3830")

    img.save(OUT)
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    main()
