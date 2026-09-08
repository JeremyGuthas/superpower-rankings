"""The weekly board as one shareable image.

A self-contained SVG — no external fonts, no scripts — so it renders the same
in a browser, a Slack unfurl or an image converter. Portrait 1080x1350 is the
shape that survives social crops.
"""
from __future__ import annotations

import html
from pathlib import Path

from .teams import info

W, H = 1080, 1350
MARGIN = 48
HEADER = 168
FOOT = 86
ROW = 58
COLS = 2
PER_COL = 16

INK = "#0e1620"
PAPER = "#ffffff"
NAVY = "#10243f"
RULE = "#c8102e"
MUTED = "#6a7887"
LINE = "#e6eaef"
UP = "#0f7b4f"
DOWN = "#c0392b"
FLAT = "#98a4b0"

DISPLAY = "'Barlow Condensed','Arial Narrow',Impact,sans-serif"
BODY = "'Barlow',Helvetica,Arial,sans-serif"
MONO = "'IBM Plex Mono','SF Mono',Menlo,monospace"


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _movement(delta) -> tuple[str, str]:
    if delta is None:
        return "NEW", MUTED
    if delta > 0:
        return f"▲{delta}", UP
    if delta < 0:
        return f"▼{abs(delta)}", DOWN
    return "–", FLAT


def render(week: dict, season: int, source_count: int) -> str:
    rows = sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"])[:COLS * PER_COL]
    col_w = (W - MARGIN * 2 - 26) / COLS
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="{BODY}" role="img" aria-label="{_esc(season)} {_esc(week["label"])} '
        f'Superpower Rankings">',
        f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
        f'<rect width="{W}" height="{HEADER - 14}" fill="{NAVY}"/>',
        f'<rect y="{HEADER - 14}" width="{W}" height="6" fill="{RULE}"/>',
        f'<text x="{MARGIN}" y="72" font-family="{DISPLAY}" font-size="54" font-weight="700" '
        f'fill="#fff" letter-spacing="1">⚡ SUPERPOWER RANKINGS</text>',
        f'<text x="{MARGIN}" y="110" font-family="{DISPLAY}" font-size="25" fill="#ffffff" '
        f'opacity=".72" letter-spacing="3">{_esc(season)} · {_esc(week["label"]).upper()} '
        f'· CONSENSUS OF {source_count} OUTLET{"" if source_count == 1 else "S"}</text>',
    ]

    for i, (abbr, entry) in enumerate(rows):
        col, idx = divmod(i, PER_COL)
        x = MARGIN + col * (col_w + 26)
        y = HEADER + 34 + idx * ROW
        team = info(abbr)
        mv, mv_color = _movement(entry.get("delta"))

        if idx:
            parts.append(f'<line x1="{x}" x2="{x + col_w - 10}" y1="{y - 30}" y2="{y - 30}" '
                         f'stroke="{LINE}" stroke-width="1"/>')
        parts += [
            f'<text x="{x + 26}" y="{y}" font-family="{MONO}" font-size="25" font-weight="600" '
            f'fill="{INK}" text-anchor="end">{entry["rank"]}</text>',
            f'<rect x="{x + 38}" y="{y - 25}" width="32" height="32" rx="7" '
            f'fill="{team["primary"]}" stroke="{team["secondary"]}" stroke-width="1.5"/>',
            f'<text x="{x + 54}" y="{y - 4}" font-family="{MONO}" font-size="12" font-weight="600" '
            f'fill="#ffffff" text-anchor="middle">{_esc(abbr)}</text>',
            f'<text x="{x + 82}" y="{y}" font-size="24" font-weight="600" fill="{INK}">'
            f'{_esc(team["nickname"])}</text>',
            f'<text x="{x + col_w - 82}" y="{y}" font-family="{MONO}" font-size="21" '
            f'font-weight="600" fill="{INK}" text-anchor="end">{entry["avg"]:.2f}</text>',
            f'<text x="{x + col_w - 12}" y="{y}" font-family="{MONO}" font-size="18" '
            f'font-weight="600" fill="{mv_color}" text-anchor="end">{_esc(mv)}</text>',
        ]

    note = week.get("storylines", {})
    tagline = ""
    if note.get("outliers"):
        o = note["outliers"][0]
        side = "higher" if o["gap"] > 0 else "lower"
        tagline = (f'Biggest disagreement: {info(o["team"])["nickname"]} — '
                   f'{abs(o["gap"])} spots {side} on one outlet than the consensus.')

    parts += [
        f'<line x1="{MARGIN}" x2="{W - MARGIN}" y1="{H - FOOT}" y2="{H - FOOT}" '
        f'stroke="{LINE}" stroke-width="1"/>',
        f'<text x="{MARGIN}" y="{H - FOOT + 30}" font-size="19" fill="{MUTED}">{_esc(tagline)}</text>',
        f'<text x="{MARGIN}" y="{H - FOOT + 58}" font-family="{DISPLAY}" font-size="19" '
        f'fill="{MUTED}" letter-spacing="2.5">SCORE = AVERAGE RANK ACROSS EVERY OUTLET '
        f'· LOWER IS BETTER</text>',
        "</svg>",
    ]
    return "\n".join(parts)


def write(week: dict, season: int, source_count: int, out_dir: Path) -> list[Path]:
    """Write week-scoped and `latest` copies. Returns the paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = render(week, season, source_count)
    paths = [out_dir / f"week-{season}-{week['week']:02d}.svg", out_dir / "latest.svg"]
    for p in paths:
        p.write_text(svg, encoding="utf-8")
    return paths
