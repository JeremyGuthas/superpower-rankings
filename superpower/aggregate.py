"""Turn a set of outlet rankings into the Superpower Ranking."""
from __future__ import annotations

import statistics
from typing import Iterable

from .teams import TEAMS


def _tiebreak(entry: dict) -> tuple:
    # Average first. Ties go to the team with the better median, then the
    # better single-outlet high, then alphabetically so output is stable.
    return (entry["avg"], entry["median"], entry["high"], entry["abbr"])


def build_week(results: Iterable, previous: dict | None = None) -> dict:
    """`results` is an iterable of SourceResult. Returns a week payload."""
    results = list(results)
    if not results:
        raise ValueError("no successful sources for this week")

    per_team: dict[str, dict[str, int]] = {a: {} for a in TEAMS}
    for res in results:
        for abbr, rank in res.ranks.items():
            per_team[abbr][res.source_id] = rank

    prev_overall = {a: t["rank"] for a, t in (previous or {}).get("teams", {}).items()}
    prev_by_source = {
        a: t.get("ranks", {}) for a, t in (previous or {}).get("teams", {}).items()
    }

    entries = []
    for abbr, ranks in per_team.items():
        vals = list(ranks.values())
        if not vals:
            continue
        entries.append({
            "abbr": abbr,
            "ranks": ranks,
            "avg": round(sum(vals) / len(vals), 2),
            "median": statistics.median(vals),
            "high": min(vals),
            "low": max(vals),
            "spread": max(vals) - min(vals),
            # Population stdev: how much the outlets disagree about this team.
            "stdev": round(statistics.pstdev(vals), 2) if len(vals) > 1 else 0.0,
            "n": len(vals),
        })

    entries.sort(key=_tiebreak)
    out: dict[str, dict] = {}
    for i, e in enumerate(entries, start=1):
        abbr = e["abbr"]
        prev = prev_overall.get(abbr)
        source_moves = {}
        for sid, rank in e["ranks"].items():
            was = prev_by_source.get(abbr, {}).get(sid)
            source_moves[sid] = (was - rank) if was is not None else None
        out[abbr] = {
            "rank": i,
            "avg": e["avg"],
            "median": e["median"],
            "high": e["high"],
            "low": e["low"],
            "spread": e["spread"],
            "stdev": e["stdev"],
            "n": e["n"],
            "ranks": e["ranks"],
            "prev": prev,
            # Positive delta = moved up the board.
            "delta": (prev - i) if prev is not None else None,
            "source_delta": source_moves,
        }
    return out


def consensus_notes(week_teams: dict) -> dict:
    """Headline facts a reader would actually want on the page."""
    if not week_teams:
        return {}
    movers = [(a, t["delta"]) for a, t in week_teams.items() if t["delta"] is not None]
    divisive = sorted(week_teams.items(), key=lambda kv: -kv[1]["spread"])
    agreed = sorted(week_teams.items(), key=lambda kv: kv[1]["spread"])
    return {
        "biggest_riser": max(movers, key=lambda kv: kv[1])[0] if movers else None,
        "biggest_faller": min(movers, key=lambda kv: kv[1])[0] if movers else None,
        "most_divisive": divisive[0][0] if divisive else None,
        "most_agreed": agreed[0][0] if agreed else None,
    }
