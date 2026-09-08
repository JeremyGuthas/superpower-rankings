"""The things an aggregator can say that no single outlet can.

Four derived views, all built from data already on the page:

* **Outliers** — where one outlet is far off the consensus on a team. This is
  the aggregator's native story: no single outlet can tell you it is the
  one out on a limb.
* **Divergence** — where a team's ranking and its actual results disagree.
* **Strength of schedule** — opponents weighted by the consensus itself, so
  the board becomes forward-looking rather than only retrospective.
* **Market gap** — where the media consensus and the betting market part ways.
"""
from __future__ import annotations

from statistics import mean

# A single outlet has to be this far from the consensus before it is worth
# calling out; below it the noise is just rounding between adjacent teams.
OUTLIER_THRESHOLD = 6
DIVERGENCE_THRESHOLD = 6
MARKET_GAP_THRESHOLD = 6


def _opponent_rank(week_teams: dict, abbr: str) -> int | None:
    entry = week_teams.get(abbr)
    return entry["rank"] if entry else None


def strength_of_schedule(week_teams: dict, log: list[dict], played_through: int) -> dict:
    """Opponents scored by their current Superpower rank (lower = tougher)."""
    played, remaining = [], []
    for g in log:
        if g["season_type"] != "regular":
            continue
        rank = _opponent_rank(week_teams, g["opponent"])
        if rank is None:
            continue
        (played if g["week"] <= played_through and g["completed"] else remaining).append(rank)
    out = {
        "sos_played": round(mean(played), 2) if played else None,
        "sos_remaining": round(mean(remaining), 2) if remaining else None,
        "opponents_remaining": len(remaining),
    }
    every = played + remaining
    out["sos_full"] = round(mean(every), 2) if every else None
    return out


def next_game(week_teams: dict, log: list[dict], played_through: int) -> dict | None:
    for g in log:
        if g["season_type"] != "regular" or g["completed"] or g["week"] <= played_through:
            continue
        return {
            "week": g["week"], "label": g["label"], "date": g["date"],
            "opponent": g["opponent"], "home": g["home"],
            "opponent_rank": _opponent_rank(week_teams, g["opponent"]),
        }
    return None


def biggest_outlier(entry: dict) -> dict | None:
    """The single outlet furthest from where the consensus put this team."""
    if len(entry.get("ranks", {})) < 3:
        return None          # with two outlets "the outlier" is meaningless
    consensus = entry["rank"]
    best = max(entry["ranks"].items(), key=lambda kv: abs(kv[1] - consensus))
    source_id, rank = best
    gap = consensus - rank   # positive: this outlet is higher on the team
    if abs(gap) < OUTLIER_THRESHOLD:
        return None
    return {"source": source_id, "rank": rank, "gap": gap}


def annotate(week: dict, games_by_team: dict, records: dict,
             standings: dict, odds: dict | None = None) -> None:
    """Attach every derived field to a week payload, in place."""
    teams = week["teams"]
    played_through = week.get("games_through", 0)
    odds_teams = (odds or {}).get("teams", {})

    for abbr, entry in teams.items():
        log = games_by_team.get(abbr, [])
        entry.update(strength_of_schedule(teams, log, played_through))
        entry["next_game"] = next_game(teams, log, played_through)
        entry["outlier"] = biggest_outlier(entry)

        # Ranked by results alone; positive divergence = the media rates this
        # team more highly than its record does.
        # Before any games are played every record is 0-0, so a "record rank"
        # would be meaningless ordering noise.
        entry["record_rank"] = standings.get(abbr) if played_through else None
        entry["divergence"] = (
            entry["record_rank"] - entry["rank"] if entry["record_rank"] else None
        )

        market = odds_teams.get(abbr)
        if market:
            entry["market_rank"] = market["market_rank"]
            entry["market_odds"] = market["american"]
            entry["market_probability"] = market["probability"]
            # Positive gap = the market is higher on this team than the media.
            entry["market_gap"] = entry["rank"] - market["market_rank"]
        else:
            entry["market_rank"] = entry["market_odds"] = None
            entry["market_probability"] = entry["market_gap"] = None

    # Rank the remaining schedule, hardest first.
    rated = [a for a, e in teams.items() if e.get("sos_remaining") is not None]
    for i, abbr in enumerate(sorted(rated, key=lambda a: teams[a]["sos_remaining"]), start=1):
        teams[abbr]["sos_rank"] = i
    for abbr in teams:
        teams[abbr].setdefault("sos_rank", None)

    week["storylines"] = storylines(week, odds)


def storylines(week: dict, odds: dict | None = None) -> dict:
    """Headline facts, ready to print as sentences on the page."""
    teams = week["teams"]

    outliers = [
        {"team": a, "source": e["outlier"]["source"], "rank": e["outlier"]["rank"],
         "consensus": e["rank"], "gap": e["outlier"]["gap"]}
        for a, e in teams.items() if e.get("outlier")
    ]
    outliers.sort(key=lambda o: -abs(o["gap"]))

    divergent = [
        {"team": a, "rank": e["rank"], "record_rank": e["record_rank"],
         "record": e.get("record"), "gap": e["divergence"]}
        for a, e in teams.items()
        if e.get("divergence") is not None and abs(e["divergence"]) >= DIVERGENCE_THRESHOLD
    ]
    divergent.sort(key=lambda d: -abs(d["gap"]))

    market = [
        {"team": a, "rank": e["rank"], "market_rank": e["market_rank"],
         "odds": e["market_odds"], "gap": e["market_gap"]}
        for a, e in teams.items()
        if e.get("market_gap") is not None and abs(e["market_gap"]) >= MARKET_GAP_THRESHOLD
    ]
    market.sort(key=lambda m: -abs(m["gap"]))

    hardest = [a for a, e in teams.items() if e.get("sos_rank") == 1]
    easiest = max((a for a, e in teams.items() if e.get("sos_rank")),
                  key=lambda a: teams[a]["sos_rank"], default=None)

    return {
        "outliers": outliers[:6],
        "divergent": divergent[:6],
        "market": market[:6],
        "market_meta": {"provider": (odds or {}).get("provider"),
                        "market": (odds or {}).get("market")} if odds else None,
        "hardest_remaining": hardest[0] if hardest else None,
        "easiest_remaining": easiest,
    }
