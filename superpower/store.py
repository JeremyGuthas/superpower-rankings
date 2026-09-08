"""Where the data lives on disk."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEEKS = DATA / "weeks"


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def week_path(season: int, week: int) -> Path:
    return WEEKS / f"{season}-week-{week:02d}.json"


def save_week(payload: dict) -> Path:
    return _write(week_path(payload["season"], payload["week"]), payload)


def load_week(season: int, week: int) -> dict | None:
    p = week_path(season, week)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def all_weeks(season: int) -> list[dict]:
    if not WEEKS.exists():
        return []
    out = []
    for p in sorted(WEEKS.glob(f"{season}-week-*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return sorted(out, key=lambda w: w["week"])


def save_site_payload(payload: dict) -> Path:
    return _write(DATA / f"season-{payload['season']}.json", payload)


def known_seasons() -> list[int]:
    if not WEEKS.exists():
        return []
    seasons = {int(p.name.split("-")[0]) for p in WEEKS.glob("*-week-*.json")}
    return sorted(seasons, reverse=True)


def save_index(payload: dict) -> Path:
    return _write(DATA / "index.json", payload)
