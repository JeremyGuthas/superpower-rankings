"""Betting-market futures, for comparing the media consensus with the money.

ESPN carries DraftKings' season futures. The Super Bowl winner market is the
useful one: it prices all 32 teams on a single scale, so it can be ranked
1-32 and set alongside the Superpower board.

American odds are converted to implied probability and then de-vigged (the
raw probabilities sum to well over 1 — that surplus is the book's margin),
so the numbers on the page are comparable between teams.
"""
from __future__ import annotations

import logging
import re

from . import http

log = logging.getLogger(__name__)

FUTURES = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/futures?limit=50"
MARKET = re.compile(r"super\s*bowl.*winner", re.I)


def american_to_probability(value: str) -> float | None:
    """+500 -> 0.1667, -150 -> 0.60."""
    v = str(value).strip().replace(" ", "")
    if not re.fullmatch(r"[+-]?\d+", v):
        return None
    n = int(v)
    if n == 0:
        return None
    return 100 / (n + 100) if n > 0 else -n / (-n + 100)


def fetch_super_bowl_odds(season: int, id_to_abbr: dict[str, str],
                          cache_hours: float = 12) -> dict:
    """{'provider': ..., 'teams': {abbr: {...}}} — empty dict if unavailable."""
    if not id_to_abbr:
        return {}
    try:
        index = http.get_json(FUTURES.format(season=season), cache_hours=cache_hours)
    except Exception as exc:
        log.warning("futures index unavailable: %s", exc)
        return {}

    market = next((i for i in index.get("items", []) if MARKET.search(i.get("name", ""))), None)
    if market is None:
        log.warning("no Super Bowl winner market in %s futures", season)
        return {}

    book = next((f for f in market.get("futures", []) if f.get("books")), None)
    if book is None:
        return {}

    raw: dict[str, dict] = {}
    for entry in book["books"]:
        ref = (entry.get("team") or {}).get("$ref", "")
        m = re.search(r"/teams/(\d+)", ref)
        if not m:
            continue
        abbr = id_to_abbr.get(m.group(1))
        prob = american_to_probability(entry.get("value", ""))
        if not abbr or prob is None:
            continue
        raw[abbr] = {"american": str(entry.get("value")), "raw_probability": prob}

    if not raw:
        return {}

    # De-vig: scale so the field sums to 1, making teams comparable.
    total = sum(v["raw_probability"] for v in raw.values())
    for v in raw.values():
        v["probability"] = round(v["raw_probability"] / total, 5)
        v["raw_probability"] = round(v["raw_probability"], 5)

    for i, abbr in enumerate(sorted(raw, key=lambda a: -raw[a]["probability"]), start=1):
        raw[abbr]["market_rank"] = i

    return {
        "market": market.get("name", "Super Bowl Winner"),
        "provider": book.get("provider", {}).get("name", "unknown"),
        "teams": raw,
    }
