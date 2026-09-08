"""Tests for the derived views: odds maths, outliers, divergence, SOS,
outlet accuracy, and the two rendered artefacts.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superpower import accuracy, analysis, digest, games, graphic, odds  # noqa: E402
from superpower.teams import TEAMS  # noqa: E402

ABBRS = sorted(TEAMS)


def week_payload(rankings: dict[str, dict[str, int]], games_through=2, **extra):
    """Build a minimal week payload from {source_id: {abbr: rank}}."""
    from superpower.aggregate import build_week

    class R:
        def __init__(self, sid, ranks):
            self.source_id, self.source_name, self.ranks = sid, sid.upper(), ranks

    teams = build_week([R(sid, r) for sid, r in rankings.items()])
    return {"season": 2026, "week": 3, "label": "Week 3",
            "games_through": games_through,
            "sources": [{"id": s, "name": s.upper()} for s in rankings],
            "teams": teams, **extra}


def straight(offset=0):
    """A 1-32 ranking, optionally rotated so outlets differ."""
    order = ABBRS[offset:] + ABBRS[:offset]
    return {a: i for i, a in enumerate(order, 1)}


# ------------------------------------------------------------------- odds

@pytest.mark.parametrize("value,expected", [
    ("+500", 1 / 6), ("+100", 0.5), ("-100", 0.5), ("-150", 0.6), ("+1000", 1 / 11),
])
def test_american_to_probability(value, expected):
    assert odds.american_to_probability(value) == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("bad", ["", "evens", "+", None, "1.5"])
def test_american_to_probability_rejects_junk(bad):
    assert odds.american_to_probability(bad) is None


def test_odds_are_devigged_and_ranked(monkeypatch):
    ids = {"1": "ARI", "2": "BUF", "3": "CHI"}
    payload = {"items": [{"name": "NFL - Super Bowl Winner", "futures": [{
        "provider": {"name": "TestBook"},
        "books": [
            {"team": {"$ref": ".../teams/1?lang=en"}, "value": "+100"},
            {"team": {"$ref": ".../teams/2?lang=en"}, "value": "+100"},
            {"team": {"$ref": ".../teams/3?lang=en"}, "value": "+300"},
        ]}]}]}
    monkeypatch.setattr(odds.http, "get_json", lambda *a, **k: payload)

    result = odds.fetch_super_bowl_odds(2026, ids)
    probs = {a: v["probability"] for a, v in result["teams"].items()}
    # Raw implied 0.5 + 0.5 + 0.25 = 1.25 of vig; de-vigged must sum to 1.
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs["ARI"] == pytest.approx(0.4)
    assert result["teams"]["CHI"]["market_rank"] == 3
    assert result["provider"] == "TestBook"


def test_odds_absent_when_market_missing(monkeypatch):
    monkeypatch.setattr(odds.http, "get_json", lambda *a, **k: {"items": []})
    assert odds.fetch_super_bowl_odds(2026, {"1": "ARI"}) == {}


def test_odds_absent_without_a_team_id_map():
    assert odds.fetch_super_bowl_odds(2026, {}) == {}


# --------------------------------------------------------------- outliers

def test_outlier_needs_three_outlets():
    two = week_payload({"a": straight(), "b": straight(4)})
    assert analysis.biggest_outlier(two["teams"][ABBRS[0]]) is None


def test_outlier_reports_the_furthest_outlet():
    ranks = {"a": straight(), "b": straight(), "c": straight()}
    wk = week_payload(ranks)
    target = ABBRS[0]
    entry = wk["teams"][target]
    entry["ranks"]["c"] = entry["rank"] + 10          # one outlet way low
    out = analysis.biggest_outlier(entry)
    assert out["source"] == "c"
    assert out["gap"] == -10                          # negative: lower than consensus


def test_small_disagreements_are_not_outliers():
    wk = week_payload({"a": straight(), "b": straight(), "c": straight()})
    entry = wk["teams"][ABBRS[0]]
    entry["ranks"]["c"] = entry["rank"] + 3
    assert analysis.biggest_outlier(entry) is None


# ------------------------------------------------- schedule + annotation

def _log(pairs, played_through):
    """pairs = [(week, opponent)] -> a team game log."""
    return [{"week": w, "label": f"Week {w}", "season_type": "regular",
             "date": "", "opponent": o, "home": w % 2 == 0,
             "points_for": 20, "points_against": 17,
             "result": "W", "completed": w <= played_through, "detail": "Final"}
            for w, o in pairs]


def test_strength_of_schedule_splits_played_and_remaining():
    wk = week_payload({"a": straight()})
    teams = wk["teams"]
    first, second, third, fourth = ABBRS[0], ABBRS[1], ABBRS[2], ABBRS[3]
    log = _log([(1, first), (2, second), (3, third), (4, fourth)], played_through=2)
    sos = analysis.strength_of_schedule(teams, log, played_through=2)
    assert sos["sos_played"] == pytest.approx(
        (teams[first]["rank"] + teams[second]["rank"]) / 2)
    assert sos["opponents_remaining"] == 2


def test_next_game_is_the_first_unplayed_fixture():
    wk = week_payload({"a": straight()})
    log = _log([(1, ABBRS[0]), (2, ABBRS[1]), (3, ABBRS[2])], played_through=2)
    nxt = analysis.next_game(wk["teams"], log, played_through=2)
    assert nxt["week"] == 3 and nxt["opponent"] == ABBRS[2]
    assert nxt["opponent_rank"] == wk["teams"][ABBRS[2]]["rank"]


def test_next_game_is_none_once_the_season_ends():
    wk = week_payload({"a": straight()})
    log = _log([(1, ABBRS[0])], played_through=1)
    assert analysis.next_game(wk["teams"], log, played_through=1) is None


def test_divergence_sign_and_preseason_guard():
    wk = week_payload({"a": straight()}, games_through=2)
    top = ABBRS[0]
    # Ranked #1 but bottom of the standings -> heavily over-rated.
    standings = {a: (32 if a == top else i) for i, a in enumerate(ABBRS, 1)}
    logs = {a: [] for a in ABBRS}
    analysis.annotate(wk, logs, {}, standings, None)
    assert wk["teams"][top]["divergence"] == 31

    pre = week_payload({"a": straight()}, games_through=0)
    analysis.annotate(pre, logs, {}, standings, None)
    assert pre["teams"][top]["record_rank"] is None
    assert pre["teams"][top]["divergence"] is None


def test_market_gap_is_positive_when_the_market_is_higher():
    wk = week_payload({"a": straight()})
    top = ABBRS[0]
    market = {"provider": "TestBook", "market": "SB",
              "teams": {top: {"market_rank": 1, "american": "+400", "probability": 0.2}}}
    # Push the team down the consensus so the market looks comparatively bullish.
    wk["teams"][top]["rank"] = 9
    analysis.annotate(wk, {a: [] for a in ABBRS}, {}, {}, market)
    assert wk["teams"][top]["market_gap"] == 8


def test_annotate_ranks_the_hardest_remaining_schedule_first():
    wk = week_payload({"a": straight()})
    easy, hard = ABBRS[0], ABBRS[1]
    logs = {a: [] for a in ABBRS}
    best, worst = sorted(wk["teams"], key=lambda a: wk["teams"][a]["rank"])[:2]
    logs[hard] = _log([(5, best)], played_through=2)     # plays the #1 team
    logs[easy] = _log([(5, ABBRS[-1])], played_through=2)
    analysis.annotate(wk, logs, {}, {}, None)
    assert wk["teams"][hard]["sos_rank"] < wk["teams"][easy]["sos_rank"]


# --------------------------------------------------------------- accuracy

def test_spearman_and_mae_bounds():
    truth = {a: i for i, a in enumerate(ABBRS, 1)}
    assert accuracy.spearman(truth, truth) == 1.0
    assert accuracy.mae(truth, truth) == 0
    flipped = {a: 33 - i for i, a in enumerate(ABBRS, 1)}
    assert accuracy.spearman(truth, flipped) == -1.0


def test_consensus_can_beat_every_outlet_that_feeds_it():
    """Two outlets wrong in opposite directions; their average is closer."""
    truth = {a: i for i, a in enumerate(ABBRS, 1)}
    shifted_up = {a: max(1, truth[a] - 4) for a in ABBRS}
    shifted_down = {a: min(32, truth[a] + 4) for a in ABBRS}

    class R:
        def __init__(self, sid, ranks):
            self.source_id, self.source_name, self.ranks = sid, sid.upper(), ranks

    from superpower.aggregate import build_week
    teams = build_week([R("up", shifted_up), R("down", shifted_down)])
    weeks = [{"week": 1, "sources": [{"id": "up", "name": "UP"}, {"id": "down", "name": "DOWN"}],
              "teams": teams}]

    scored = accuracy.score_season(weeks, truth, True, {"up": "UP", "down": "DOWN"})
    assert scored["available"]
    assert scored["consensus"]["mae"] < min(r["mae"] for r in scored["sources"])
    assert scored["summary"]["outlets_that_beat_it"] == []


def test_accuracy_unavailable_before_any_games():
    assert accuracy.score_season([], {}, False, {})["available"] is False


def test_accuracy_skips_weeks_a_source_missed():
    truth = {a: i for i, a in enumerate(ABBRS, 1)}
    full = week_payload({"a": straight()})
    partial = week_payload({"a": straight()})
    for entry in partial["teams"].values():
        entry["ranks"] = {}                      # source absent that week
    scored = accuracy.score_season([full, partial], truth, True, {"a": "A"})
    assert scored["sources"][0]["weeks"] == 1


# ------------------------------------------------------- rendered output

def test_standings_order_by_record_then_differential():
    recs = {
        "BUF": {"win_pct": 1.0, "differential": 10},
        "KC":  {"win_pct": 1.0, "differential": 40},
        "NYJ": {"win_pct": 0.0, "differential": -30},
    }
    order = games.standings(recs)
    assert order["KC"] == 1 and order["BUF"] == 2 and order["NYJ"] == 3


def test_graphic_is_wellformed_svg_naming_the_leader():
    import xml.etree.ElementTree as ET
    wk = week_payload({"a": straight(), "b": straight(1), "c": straight(2)})
    analysis.annotate(wk, {a: [] for a in ABBRS}, {}, {}, None)
    svg = graphic.render(wk, 2026, 3)
    root = ET.fromstring(svg)          # raises if the SVG is malformed
    assert root.tag.endswith("svg")
    leader = min(wk["teams"], key=lambda a: wk["teams"][a]["rank"])
    assert leader in svg


def test_digest_is_html_listing_the_top_teams():
    wk = week_payload({"a": straight(), "b": straight(1), "c": straight(2)})
    analysis.annotate(wk, {a: [] for a in ABBRS}, {}, {}, None)
    wk["sources"] = [{"id": "a", "name": "A", "url": "https://example.com/a", "title": "A ranks"}]
    site = {"season": 2026, "sources": [{"id": "a", "name": "A"}]}
    doc = digest.build(site, wk, "https://example.com")
    assert doc.startswith("<!doctype html>")
    leader = min(wk["teams"], key=lambda a: wk["teams"][a]["rank"])
    from superpower.teams import info
    assert info(leader)["name"] in doc
    assert "https://example.com/a" in doc


def test_digest_refuses_to_send_without_configuration(monkeypatch):
    for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_FROM"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit) as exc:
        digest.send("<p>hi</p>", "subject", ["a@example.com"])
    assert "SMTP_HOST" in str(exc.value)
