"""CLI entry point: fetch, aggregate, and write the site payload."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from . import games as games_mod
from . import season as season_mod
from . import store
from .aggregate import build_week, consensus_notes
from .extract import RankParseError, extract
from .sources import SourceResult, enabled_sources
from .teams import all_teams

log = logging.getLogger("superpower")


def collect(season: int, week: int, sources, live: bool = True
            ) -> tuple[list[SourceResult], list[dict]]:
    ok: list[SourceResult] = []
    failed: list[dict] = []
    for src in sources:
        if not live and not src.supports_history:
            failed.append({"id": src.id, "name": src.name,
                           "error": "no archive for past weeks — this outlet "
                                    "publishes to a single rolling URL"})
            continue
        try:
            article = src.load(src.find_article(season, week))
            ranks, strategy = extract(article.markup)
        except RankParseError as exc:
            failed.append({"id": src.id, "name": src.name,
                           "error": f"could not parse a full 1-32 ranking ({exc})"})
            log.warning("%s: parse failed: %s", src.id, exc)
            continue
        except Exception as exc:
            failed.append({"id": src.id, "name": src.name,
                           "error": f"{type(exc).__name__}: {exc}"})
            log.warning("%s: %s: %s", src.id, type(exc).__name__, exc)
            continue
        ok.append(SourceResult(src.id, src.name, article, ranks, strategy))
        log.info("%s: parsed 32 teams via %s", src.id, strategy)
    return ok, failed


def build(season: int, week: int, sources, game_log: dict, live: bool = True) -> dict:
    results, failed = collect(season, week, sources, live=live)
    if not results:
        raise SystemExit(f"no source produced a usable ranking for {season} week {week}")

    previous = store.load_week(season, week - 1) if week > 1 else None
    teams = build_week(results, previous)

    # "Week N rankings" react to the games played through week N-1.
    played = season_mod.games_through(week)
    recs = games_mod.records(game_log, through_week=played)
    for abbr, entry in teams.items():
        rec = recs.get(abbr, {})
        entry["record"] = rec.get("record", "0-0")
        entry["differential"] = rec.get("differential", 0)
        entry["last_game"] = next(
            (g for g in reversed(game_log.get(abbr, []))
             if g["completed"] and g["week"] <= played
             and g["season_type"] == "regular"),
            None,
        )

    return {
        "season": season,
        "week": week,
        "label": season_mod.week_label(week),
        "games_through": season_mod.games_through(week),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": [{
            "id": r.source_id, "name": r.source_name, "url": r.article.url,
            "title": r.article.title, "author": r.article.author,
            "published": r.article.published, "strategy": r.strategy,
            "fetched": r.fetched,
        } for r in results],
        "failed_sources": failed,
        "notes": consensus_notes(teams),
        "teams": teams,
    }


def compile_site(season: int, game_log: dict) -> dict:
    weeks = store.all_weeks(season)
    src_meta: dict[str, dict] = {}
    for w in weeks:
        for s in w["sources"]:
            src_meta.setdefault(s["id"], {"id": s["id"], "name": s["name"]})
    return {
        "season": season,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "teams": all_teams(),
        "sources": list(src_meta.values()),
        "weeks": weeks,
        "games": game_log,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="superpower", description=__doc__)
    p.add_argument("--season", type=int, default=None)
    p.add_argument("--week", type=int, default=None, help="defaults to the current week")
    p.add_argument("--only", nargs="*", help="restrict to these source ids")
    p.add_argument("--exclude", nargs="*", help="skip these source ids")
    p.add_argument("--backfill", action="store_true",
                   help="also rebuild every earlier week that has no data yet")
    p.add_argument("--compile-only", action="store_true",
                   help="skip fetching; just rebuild the site payload from stored weeks")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    season = args.season or season_mod.current_season()
    week = args.week or season_mod.current_week(season)
    sources = enabled_sources(args.only, args.exclude)

    game_log = games_mod.team_games(games_mod.fetch_season(season, through_week=week))

    if not args.compile_only:
        wanted = range(1, week + 1) if args.backfill else [week]
        for wk in wanted:
            if args.backfill and wk != week and store.load_week(season, wk):
                continue
            try:
                payload = build(season, wk, sources, game_log,
                                live=(wk == week and season == season_mod.current_season()))
            except SystemExit as exc:
                log.error("week %s skipped: %s", wk, exc)
                continue
            path = store.save_week(payload)
            top = min(payload["teams"], key=lambda a: payload["teams"][a]["rank"])
            print(f"week {wk:>2}: {len(payload['sources'])} sources, "
                  f"#1 {top}  ->  {path.name}")

    site = compile_site(season, game_log)
    store.save_site_payload(site)
    print(f"compiled {len(site['weeks'])} week(s) -> data/season-{season}.json")

    # The index lists every season that has data, so the site can offer an archive.
    seasons = []
    for yr in store.known_seasons():
        weeks = store.all_weeks(yr)
        if not weeks:
            continue
        seasons.append({
            "season": yr,
            "latest_week": max(w["week"] for w in weeks),
            "weeks": [{"week": w["week"], "label": w["label"],
                       "sources": len(w["sources"])} for w in weeks],
        })
    store.save_index({
        "generated": site["generated"],
        "default_season": season,
        "seasons": seasons,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
