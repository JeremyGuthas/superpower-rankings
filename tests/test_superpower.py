"""Tests for the parts that break silently: name matching, rank extraction,
the ranking-week calendar, and the aggregate itself.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superpower import aggregate, extract, season, teams  # noqa: E402
from superpower.sources import BY_ID  # noqa: E402

ORDER = [
    "Los Angeles Rams", "Seattle Seahawks", "Buffalo Bills", "Denver Broncos",
    "Philadelphia Eagles", "New England Patriots", "Green Bay Packers",
    "Baltimore Ravens", "Houston Texans", "Jacksonville Jaguars",
    "Dallas Cowboys", "San Francisco 49ers", "Detroit Lions", "Kansas City Chiefs",
    "Cincinnati Bengals", "Tampa Bay Buccaneers", "Los Angeles Chargers",
    "Minnesota Vikings", "Washington Commanders", "Arizona Cardinals",
    "Chicago Bears", "Pittsburgh Steelers", "Indianapolis Colts", "Atlanta Falcons",
    "Miami Dolphins", "New York Jets", "New Orleans Saints", "Carolina Panthers",
    "New York Giants", "Las Vegas Raiders", "Cleveland Browns", "Tennessee Titans",
]


# --------------------------------------------------------------- team names

@pytest.mark.parametrize("raw,expected", [
    ("Los Angeles Rams", "LAR"), ("LA Rams", "LAR"), ("L.A. Rams", "LAR"),
    ("Rams", "LAR"), ("St. Louis Rams", "LAR"),
    ("N.Y. Giants", "NYG"), ("New York Jets", "NYJ"), ("Jets", "NYJ"),
    ("49ers", "SF"), ("Niners", "SF"), ("San Francisco 49ers", "SF"),
    ("Washington", "WSH"), ("WAS", "WSH"), ("Commanders", "WSH"),
    ("Bucs", "TB"), ("Tampa Bay Buccaneers", "TB"),
    ("Jacksonville Jaguars (2-0)", "JAX"),
    ("Oakland Raiders", "LV"), ("San Diego Chargers", "LAC"),
])
def test_resolve(raw, expected):
    assert teams.resolve(raw) == expected


def test_every_team_resolves_from_its_own_names():
    for abbr in teams.TEAMS:
        info = teams.info(abbr)
        assert teams.resolve(info["name"]) == abbr
        assert teams.resolve(info["nickname"]) == abbr
        assert teams.resolve(abbr) == abbr


def test_bare_shared_city_does_not_resolve():
    # "Los Angeles" and "New York" are shared, so they must stay ambiguous.
    assert teams.resolve("Los Angeles") is None
    assert teams.resolve("New York") is None


def test_longest_alias_wins():
    assert teams.find_in_text("1. Los Angeles Chargers") == "LAC"
    assert teams.find_in_text("1. Los Angeles Rams") == "LAR"


# ---------------------------------------------------------------- extraction

def test_headings_strategy():
    markup = "".join(f"<h2>{i}. {n}</h2><p>blurb</p>" for i, n in enumerate(ORDER, 1))
    ranks, strategy = extract.extract(markup)
    assert strategy == "headings"
    assert ranks["LAR"] == 1 and ranks["TEN"] == 32


def test_rank_label_strategy():
    markup = "".join(f"<div>Rank</div><div>{i}</div><div>{n}</div><p>blurb</p>"
                     for i, n in enumerate(ORDER, 1))
    ranks, strategy = extract.extract(markup)
    assert strategy == "rank-label"
    assert ranks["SEA"] == 2


def test_split_lines_strategy():
    rows = "".join(f"<tr><td>{i}</td><td>{n.split()[-1]}</td>"
                   f"<td>a long analytical blurb about the team</td></tr>"
                   for i, n in enumerate(ORDER, 1))
    ranks, strategy = extract.extract(f"<table>{rows}</table>")
    assert strategy == "split-lines"
    assert ranks["LAR"] == 1


def test_numbered_lines_strategy():
    markup = "<p>" + "</p><p>".join(f"{i}. {n}" for i, n in enumerate(ORDER, 1)) + "</p>"
    ranks, _ = extract.extract(markup)
    assert len(ranks) == 32


def test_incomplete_ranking_is_rejected():
    markup = "".join(f"<h2>{i}. {n}</h2>" for i, n in enumerate(ORDER[:20], 1))
    with pytest.raises(extract.RankParseError):
        extract.extract(markup)


def test_duplicate_team_is_rejected():
    bad = ORDER[:31] + ["Los Angeles Rams"]          # Rams listed twice
    markup = "".join(f"<h2>{i}. {n}</h2>" for i, n in enumerate(bad, 1))
    with pytest.raises(extract.RankParseError):
        extract.extract(markup)


def test_validate_rejects_non_permutation():
    with pytest.raises(extract.RankParseError):
        extract.validate([(1, a) for a in teams.TEAMS])


def test_cross_references_in_prose_do_not_shift_ranks():
    # Outlets constantly name other teams inside a blurb; first mention wins.
    markup = "".join(
        f"<h2>{i}. {n}</h2><p>They beat the Kansas City Chiefs and the Jets.</p>"
        for i, n in enumerate(ORDER, 1))
    ranks, _ = extract.extract(markup)
    assert ranks["KC"] == 14 and ranks["NYJ"] == 26


# ------------------------------------------------------------------ calendar

@pytest.mark.parametrize("day,expected", [
    ("2026-09-07", 1),    # before kickoff
    ("2026-09-10", 1),    # kickoff Thursday
    ("2026-09-14", 1),    # Monday night of Week 1
    ("2026-09-15", 2),    # Tuesday -> outlets publish "Week 2"
    ("2026-09-21", 2),
    ("2026-09-22", 3),
    ("2027-01-05", 18),
])
def test_ranking_week_rolls_over_on_tuesday(day, expected):
    y, m, d = map(int, day.split("-"))
    assert season.current_week(2026, date(y, m, d)) == expected


def test_games_through_lags_the_ranking_week():
    assert season.games_through(1) == 0
    assert season.games_through(8) == 7


# ----------------------------------------------------------------- aggregate

class FakeResult:
    def __init__(self, sid, ranks):
        self.source_id = sid
        self.source_name = sid.upper()
        self.ranks = ranks


def _ranking(order):
    return {teams.resolve(n): i for i, n in enumerate(order, 1)}


def test_average_and_ordering():
    a = _ranking(ORDER)
    swapped = ORDER[:]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    b = _ranking(swapped)

    week = aggregate.build_week([FakeResult("a", a), FakeResult("b", b)])
    assert week["LAR"]["avg"] == 1.5 and week["SEA"]["avg"] == 1.5
    # Tie on average -> broken by median, then best single rank; both teams
    # still occupy ranks 1 and 2 with no duplicates.
    assert {week["LAR"]["rank"], week["SEA"]["rank"]} == {1, 2}
    assert week["LAR"]["spread"] == 1
    assert week["TEN"]["rank"] == 32


def test_deltas_are_positive_when_a_team_climbs():
    first = aggregate.build_week([FakeResult("a", _ranking(ORDER))])
    moved = ORDER[:]
    moved.insert(0, moved.pop(4))          # Eagles jump 5th -> 1st
    second = aggregate.build_week([FakeResult("a", _ranking(moved))],
                                  previous={"teams": first})
    assert second["PHI"]["rank"] == 1
    assert second["PHI"]["delta"] == 4
    assert second["PHI"]["source_delta"]["a"] == 4
    assert second["LAR"]["delta"] == -1


def test_first_week_has_no_movement():
    week = aggregate.build_week([FakeResult("a", _ranking(ORDER))])
    assert week["LAR"]["prev"] is None and week["LAR"]["delta"] is None


def test_consensus_notes():
    a = _ranking(ORDER)
    wild = ORDER[:]
    wild.insert(0, wild.pop(20))           # Bears 21st -> 1st on one outlet
    week = aggregate.build_week([FakeResult("a", a), FakeResult("b", _ranking(wild))])
    assert aggregate.consensus_notes(week)["most_divisive"] == "CHI"


# -------------------------------------------------------- source safety net

def test_rolling_url_sources_cannot_backfill_history():
    """A single-URL outlet always shows *today's* list, so it must never be
    filed under a past week."""
    for sid in ("cbs", "sharpfootball"):
        assert BY_ID[sid].supports_history is False
    assert BY_ID["espn"].supports_history is True


# --------------------------------------- regression: the ticker incident
#
# NFL.com's in-season format inserts a movement arrow and a "No Rank change"
# caption between the rank number and the team. The parser missed the team,
# the ordering fallback then read the page's *fixture ticker* as a ranking,
# and because that fallback numbers teams 1..32 by order of appearance it
# produced a structurally perfect — and completely wrong — board.

NFL_INSEASON = "".join(
    f"<div>Rank</div><div>{i}</div><div>—</div><div>No Rank change</div>"
    f"<div>{n}</div><p>A paragraph about the team.</p>"
    for i, n in enumerate(ORDER, 1))


def test_rank_label_survives_movement_captions():
    ranks, strategy = extract.extract(NFL_INSEASON)
    assert strategy == "rank-label"
    assert ranks["LAR"] == 1 and ranks["TEN"] == 32


def test_no_rank_change_is_not_the_new_orleans_saints():
    # "no" is New Orleans' abbreviation and also an English word.
    assert teams.resolve_exact("No Rank change") is None
    assert teams.resolve("No Rank change") is None
    assert teams.resolve_exact("New Orleans Saints") == "NO"
    assert teams.resolve_exact("NO") == "NO"


@pytest.mark.parametrize("phrase", [
    "No Rank change", "no change", "Not ranked", "Next up", "No movement",
])
def test_short_abbreviations_never_match_inside_prose(phrase):
    assert teams.find_in_text(phrase) is None


def test_ordering_fallback_is_gone():
    """A strategy that numbers teams by order of appearance can never fail
    validation, so validation offers it no protection. It must not exist."""
    assert not hasattr(extract, "from_bare_sequence")
    assert "bare-sequence" not in {name for name, _ in extract.STRATEGIES}


def test_a_page_of_team_names_in_the_wrong_order_is_rejected():
    ticker = "".join(f"<div>{n}</div><div>{teams.resolve(n)}</div>"
                     for n in reversed(ORDER))
    with pytest.raises(extract.RankParseError):
        extract.extract(ticker)


# ------------------------------------------------ cross-source agreement

class _Src:
    def __init__(self, sid, ranks):
        self.source_id, self.source_name, self.ranks = sid, sid.upper(), ranks


def _perm(order):
    return {teams.resolve(n): i for i, n in enumerate(order, 1)}


def test_cross_check_drops_a_source_that_agrees_with_nobody():
    good = _perm(ORDER)
    nudged = {a: max(1, min(32, r + (1 if r % 3 else -1))) for a, r in good.items()}
    reversed_ = _perm(list(reversed(ORDER)))
    kept, dropped = aggregate.cross_check(
        [_Src("a", good), _Src("b", nudged), _Src("c", dict(good)), _Src("bad", reversed_)])
    assert [s.source_id for s in kept] == ["a", "b", "c"]
    assert len(dropped) == 1 and dropped[0]["id"] == "bad"
    assert "parsing failure" in dropped[0]["error"]


def test_cross_check_keeps_genuine_disagreement():
    """Outlets really do differ. Only a mis-parse lands near zero."""
    good = _perm(ORDER)
    spicy = dict(good)
    # Move four teams a long way — a contrarian board, not a broken one.
    for abbr, rank in list(spicy.items())[:4]:
        spicy[abbr] = min(32, rank + 12)
    kept, dropped = aggregate.cross_check(
        [_Src("a", good), _Src("b", dict(good)), _Src("c", spicy)])
    assert dropped == []
    assert len(kept) == 3


def test_cross_check_declines_to_judge_two_sources():
    good = _perm(ORDER)
    reversed_ = _perm(list(reversed(ORDER)))
    kept, dropped = aggregate.cross_check([_Src("a", good), _Src("bad", reversed_)])
    assert len(kept) == 2 and dropped == []
