"""Score the outlets against what actually happened.

Every week each outlet commits to an order for all 32 teams. Once games have
been played, that order can be checked: how far was each team from where it
finished? Two measures, both against the same yardstick (final order by win
percentage, then point differential):

* **MAE** — mean absolute error in places. "Off by 4.2 spots on average."
* **Spearman** — rank correlation, 1.0 for a perfect call, 0 for noise.

The interesting question is whether the average beats its own ingredients, so
the consensus is scored on exactly the same footing as the outlets.
"""
from __future__ import annotations

from statistics import mean

# Rankings published before any games are guesswork about the season ahead,
# not a read on it; they are scored separately as "preseason conviction".
EARLY_WEEKS = 6


def spearman(a: dict[str, int], b: dict[str, int]) -> float | None:
    shared = set(a) & set(b)
    n = len(shared)
    if n < 3:
        return None
    d2 = sum((a[k] - b[k]) ** 2 for k in shared)
    return round(1 - (6 * d2) / (n * (n * n - 1)), 4)


def mae(a: dict[str, int], b: dict[str, int]) -> float | None:
    shared = set(a) & set(b)
    if not shared:
        return None
    return round(mean(abs(a[k] - b[k]) for k in shared), 3)


def _series(weeks: list[dict], pick) -> list[tuple[int, dict[str, int]]]:
    """[(week, {abbr: rank})] for whichever ranking `pick` pulls out."""
    out = []
    for w in weeks:
        ranking = {}
        for abbr, entry in w["teams"].items():
            r = pick(entry)
            if r is not None:
                ranking[abbr] = r
        if len(ranking) == 32:
            out.append((w["week"], ranking))
    return out


def _score(series, truth: dict[str, int]) -> dict | None:
    if not series:
        return None
    per_week = [
        {"week": wk, "mae": mae(ranking, truth), "spearman": spearman(ranking, truth)}
        for wk, ranking in series
    ]
    scored = [p for p in per_week if p["mae"] is not None]
    if not scored:
        return None
    early = [p for p in scored if p["week"] <= EARLY_WEEKS]
    best = min(scored, key=lambda p: p["mae"])
    worst = max(scored, key=lambda p: p["mae"])
    return {
        "weeks": len(scored),
        "mae": round(mean(p["mae"] for p in scored), 3),
        "spearman": round(mean(p["spearman"] for p in scored if p["spearman"] is not None), 4),
        "early_mae": round(mean(p["mae"] for p in early), 3) if early else None,
        "best_week": {"week": best["week"], "mae": best["mae"]},
        "worst_week": {"week": worst["week"], "mae": worst["mae"]},
        "by_week": per_week,
    }


def score_season(weeks: list[dict], standings: dict[str, int],
                 games_played: bool, source_names: dict[str, str]) -> dict:
    """Rank every outlet — and the consensus — by how close they came."""
    if not weeks or not games_played or len(standings) != 32:
        return {"available": False,
                "reason": "no completed games to score against yet"}

    rows = []
    ids = sorted({sid for w in weeks for s in w["sources"] for sid in [s["id"]]})
    for sid in ids:
        scored = _score(_series(weeks, lambda e, s=sid: e["ranks"].get(s)), standings)
        if scored:
            rows.append({"id": sid, "name": source_names.get(sid, sid), **scored})

    consensus = _score(_series(weeks, lambda e: e["rank"]), standings)
    rows.sort(key=lambda r: r["mae"])
    for i, r in enumerate(rows, start=1):
        r["place"] = i

    beat = None
    if consensus and rows:
        better = [r for r in rows if r["mae"] < consensus["mae"]]
        beat = {"consensus_mae": consensus["mae"],
                "outlets_that_beat_it": [r["id"] for r in better],
                "outlets_scored": len(rows)}

    return {
        "available": True,
        "basis": "final order by win percentage, then point differential",
        "sources": rows,
        "consensus": ({"id": "consensus", "name": "Superpower consensus", **consensus}
                      if consensus else None),
        "summary": beat,
    }
