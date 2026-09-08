#!/usr/bin/env python3
"""Bundle the whole site into one self-contained HTML file.

Everything — every season's data, the styles, the script — is inlined, so the
result can be published as an Artifact, emailed, or opened straight off disk.
It is a *snapshot*: it shows the data as of the moment it was built and does
not update itself. The hosted site under `site/` is the live one.

    python snapshot/build.py [-o out.html]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"


def build() -> str:
    seasons = {}
    for path in sorted(DATA.glob("season-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        seasons[str(payload["season"])] = payload
    if not seasons:
        raise SystemExit("no season data yet — run `python -m superpower.run` first")

    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    blob = json.dumps(
        {"default_season": str(index["default_season"]), "seasons": seasons},
        separators=(",", ":"),
    ).replace("</", "<\\/")   # never let team text close the script tag early

    return "\n".join([
        (HERE / "head.html").read_text(encoding="utf-8"),
        (HERE / "body.html").read_text(encoding="utf-8"),
        f'<script id="spr-data" type="application/json">{blob}</script>',
        "<script>window.__SPR__ = "
        "JSON.parse(document.getElementById('spr-data').textContent);</script>",
        "<script>",
        (HERE / "app.js").read_text(encoding="utf-8"),
        "</script>",
        "",
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default=str(ROOT / "dist" / "superpower-rankings.html"))
    ap.add_argument("--standalone", action="store_true",
                    help="add <!doctype> and charset so the file opens directly "
                         "in a browser (the Artifact wrapper supplies these itself)")
    args = ap.parse_args()

    html = build()
    if args.standalone:
        html = ('<!doctype html><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                + html)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out}  ({len(html.encode()) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
