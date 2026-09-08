"""Social share cards.

Facebook, X, Slack and Reddit will not render an SVG in a link preview, so
the weekly SVG graphic cannot double as the Open Graph image. These are real
1200x630 PNGs, drawn with the site's own typefaces (vendored under
assets/fonts/, OFL licensed) so a build machine needs no system fonts.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .teams import info

W, H = 1200, 630
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

NAVY = (16, 36, 63)
RULE = (200, 16, 46)
INK = (14, 22, 32)
PAPER = (255, 255, 255)
MUTED = (106, 120, 135)
LINE = (223, 229, 235)
UP = (15, 123, 79)
DOWN = (192, 57, 43)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


def _hex(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _luminance(rgb: tuple[int, int, int]) -> float:
    def lin(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _on(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return INK if _luminance(rgb) > 0.42 else PAPER


def _chip(d: ImageDraw.ImageDraw, x: int, y: int, size: int, abbr: str) -> None:
    t = info(abbr)
    primary = _hex(t["primary"])
    d.rounded_rectangle([x, y, x + size, y + size], radius=size // 4,
                        fill=primary, outline=_hex(t["secondary"]), width=2)
    f = _font("Barlow-SemiBold", int(size * 0.36))
    box = d.textbbox((0, 0), abbr, font=f)
    d.text((x + (size - (box[2] - box[0])) / 2 - box[0],
            y + (size - (box[3] - box[1])) / 2 - box[1]),
           abbr, font=f, fill=_on(primary))


def _header(d: ImageDraw.ImageDraw, eyebrow: str) -> None:
    d.rectangle([0, 0, W, 108], fill=NAVY)
    d.rectangle([0, 108, W, 114], fill=RULE)
    d.text((48, 26), "SUPERPOWER RANKINGS", font=_font("BarlowCondensed-Bold", 52),
           fill=PAPER)
    d.text((48, 78), eyebrow.upper(), font=_font("BarlowCondensed-Medium", 23),
           fill=(178, 194, 212))


def _footer(d: ImageDraw.ImageDraw, note: str) -> None:
    d.line([48, H - 62, W - 48, H - 62], fill=LINE, width=1)
    d.text((48, H - 50), note, font=_font("Barlow-Regular", 20), fill=MUTED)
    d.text((W - 48, H - 50), "superpowerrankings.com",
           font=_font("Barlow-SemiBold", 20), fill=MUTED, anchor="ra")


def week_card(week: dict, season: int, sources: int) -> Image.Image:
    """Top ten plus movement — the shape that reads at thumbnail size."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    _header(d, f"{season} · {week['label']} · consensus of {sources} "
               f"outlet{'' if sources == 1 else 's'}")

    rows = sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"])[:10]
    f_rank = _font("Barlow-SemiBold", 30)
    f_team = _font("Barlow-SemiBold", 27)
    f_num = _font("Barlow-SemiBold", 24)
    top = 146

    # Two columns of five: ten teams is what stays readable in a thumbnail.
    for i, (abbr, e) in enumerate(rows):
        col_x = 48 if i < 5 else 636
        row_y = top + (i % 5) * 76

        d.text((col_x + 34, row_y + 8), str(e["rank"]), font=f_rank, fill=INK, anchor="ra")
        _chip(d, col_x + 48, row_y + 6, 38, abbr)
        d.text((col_x + 98, row_y + 10), info(abbr)["nickname"], font=f_team, fill=INK)
        d.text((col_x + 470, row_y + 12), f"{e['avg']:.2f}", font=f_num, fill=INK, anchor="ra")

        delta = e.get("delta")
        if delta:
            mark = f"▲{delta}" if delta > 0 else f"▼{abs(delta)}"
            d.text((col_x + 520, row_y + 13), mark, font=_font("Barlow-SemiBold", 21),
                   fill=UP if delta > 0 else DOWN, anchor="ra")

    story = (week.get("storylines") or {}).get("outliers") or []
    note = "Score = average rank across every outlet · lower is better"
    if story:
        o = story[0]
        side = "higher" if o["gap"] > 0 else "lower"
        note = (f"Biggest disagreement: {info(o['team'])['nickname']}, "
                f"{abs(o['gap'])} spots {side} on one outlet")
    _footer(d, note)
    return img


def team_card(abbr: str, week: dict, season: int) -> Image.Image:
    t = info(abbr)
    e = week["teams"][abbr]
    primary = _hex(t["primary"])
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 300], fill=primary)
    fg = _on(primary)
    _chip(d, 48, 96, 110, abbr)
    d.text((186, 104), t["location"].upper(), font=_font("BarlowCondensed-Medium", 40), fill=fg)
    d.text((186, 148), t["nickname"].upper(), font=_font("BarlowCondensed-Bold", 76), fill=fg)
    d.text((186, 238), f"{t['division']} · {season} {week['label']}",
           font=_font("Barlow-Regular", 24), fill=fg)

    stats = [("SUPERPOWER", f"#{e['rank']}"), ("SCORE", f"{e['avg']:.2f}"),
             ("OUTLET HIGH/LOW", f"{e['high']}–{e['low']}"),
             ("RECORD", e.get("record", "0-0"))]
    for i, (label, value) in enumerate(stats):
        x = 48 + i * 288
        d.text((x, 372), value, font=_font("Barlow-SemiBold", 62), fill=INK)
        d.text((x, 452), label, font=_font("BarlowCondensed-Medium", 24), fill=MUTED)

    _footer(d, "Consensus of every major NFL power ranking")
    return img


def write(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path
