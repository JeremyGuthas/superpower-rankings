"""Schedule, scores and records, from ESPN's public scoreboard feed.

Team pages need more than a rank line: what the team actually did that week,
who it played, and what the result was. This module pulls the full regular
season (plus playoffs) and derives running records.
"""
from __future__ import annotations

import logging

from . import http
from .teams import TEAMS, resolve

log = logging.getLogger(__name__)

SCOREBOARD = ("https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/"
              "scoreboard?dates={season}&seasontype={stype}&week={week}")

REGULAR_SEASON_WEEKS = 18
POSTSEASON_WEEKS = {1: "Wild Card", 2: "Divisional", 3: "Conference", 5: "Super Bowl"}


#: ESPN numeric team id -> canonical abbreviation, filled in as scoreboards
#: are parsed so the odds feed can be joined without extra requests.
TEAM_IDS: dict[str, str] = {}


def _fetch_week(season: int, week: int, stype: int, cache_hours: float) -> list[dict]:
    url = SCOREBOARD.format(season=season, stype=stype, week=week)
    try:
        data = http.get_json(url, cache_hours=cache_hours)
    except Exception as exc:
        log.warning("scoreboard %s wk%s type%s failed: %s", season, week, stype, exc)
        return []

    games = []
    for event in data.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        status = comp.get("status", {}).get("type", {})
        sides = {}
        for c in comp.get("competitors", []):
            team = c.get("team", {})
            abbr = resolve(team.get("abbreviation", "")) or resolve(team.get("displayName", ""))
            if not abbr:
                continue
            if team.get("id"):
                TEAM_IDS[str(team["id"])] = abbr
            score = c.get("score")
            sides[c.get("homeAway", "home")] = {
                "team": abbr,
                "score": int(score) if str(score).lstrip("-").isdigit() else None,
                "winner": c.get("winner"),
            }
        if "home" not in sides or "away" not in sides:
            continue
        games.append({
            "id": event.get("id"),
            "season": season,
            "week": week,
            "season_type": "post" if stype == 3 else "regular",
            "label": POSTSEASON_WEEKS.get(week, f"Week {week}") if stype == 3 else f"Week {week}",
            "date": event.get("date"),
            "state": status.get("state"),          # pre | in | post
            "completed": bool(status.get("completed")),
            "detail": status.get("shortDetail", ""),
            "home": sides["home"],
            "away": sides["away"],
        })
    return games


def fetch_season(season: int, through_week: int | None = None,
                 include_postseason: bool = True) -> list[dict]:
    """Every fixture in the season, played or not.

    `through_week` only tunes caching — the full schedule is always returned,
    because strength of schedule and "next opponent" need future fixtures.
    """
    live = through_week or REGULAR_SEASON_WEEKS
    out: list[dict] = []
    for week in range(1, REGULAR_SEASON_WEEKS + 1):
        # Finished weeks never change; the current one and anything ahead of
        # it can still move, so they get a short cache.
        cache = 24 * 14 if week < live - 1 else 1
        out.extend(_fetch_week(season, week, 2, cache))
    if include_postseason and live >= REGULAR_SEASON_WEEKS:
        for week in POSTSEASON_WEEKS:
            out.extend(_fetch_week(season, week, 3, 24))
    return out


def team_games(games: list[dict]) -> dict[str, list[dict]]:
    """Flatten the schedule into a per-team, chronological game log."""
    by_team: dict[str, list[dict]] = {a: [] for a in TEAMS}
    for g in games:
        for side, other in (("home", "away"), ("away", "home")):
            abbr = g[side]["team"]
            if abbr not in by_team:
                continue
            us, them = g[side], g[other]
            result = None
            if g["completed"] and us["score"] is not None and them["score"] is not None:
                result = "W" if us["score"] > them["score"] else "L" if us["score"] < them["score"] else "T"
            by_team[abbr].append({
                "week": g["week"],
                "label": g["label"],
                "season_type": g["season_type"],
                "date": g["date"],
                "opponent": them["team"],
                "home": side == "home",
                "points_for": us["score"],
                "points_against": them["score"],
                "result": result,
                "completed": g["completed"],
                "detail": g["detail"],
            })
    for log_ in by_team.values():
        log_.sort(key=lambda x: (x["season_type"] == "post", x["week"]))
    return by_team


def standings(recs: dict[str, dict]) -> dict[str, int]:
    """Rank all 32 teams by result alone: win pct, then point differential.

    This is the yardstick the site scores outlets against — not an official
    playoff-seeding tiebreak, just "who actually won games".
    """
    order = sorted(recs, key=lambda a: (-recs[a]["win_pct"], -recs[a]["differential"], a))
    return {abbr: i for i, abbr in enumerate(order, start=1)}


def records(by_team: dict[str, list[dict]], through_week: int | None = None) -> dict[str, dict]:
    """Running W-L-T and point differential, optionally as of a given week."""
    out = {}
    for abbr, log_ in by_team.items():
        w = l = t = pf = pa = 0
        for g in log_:
            if not g["completed"] or g["season_type"] != "regular":
                continue
            if through_week is not None and g["week"] > through_week:
                continue
            pf += g["points_for"] or 0
            pa += g["points_against"] or 0
            w += g["result"] == "W"
            l += g["result"] == "L"
            t += g["result"] == "T"
        played = w + l + t
        out[abbr] = {
            "wins": w, "losses": l, "ties": t,
            "record": f"{w}-{l}" + (f"-{t}" if t else ""),
            "points_for": pf, "points_against": pa, "differential": pf - pa,
            "win_pct": round((w + 0.5 * t) / played, 3) if played else 0.0,
        }
    return out
