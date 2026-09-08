"""Season calendar helpers.

The NFL season pivots on Tuesdays: games finish Monday night, outlets publish
their new rankings Tuesday morning, so "week N" of rankings reflects the games
played in week N.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Week 1 kickoff (Thursday) per season. Add a season here each year, or let
# `kickoff_for` fall back to the NFL's rule of thumb.
KICKOFFS = {
    2024: date(2024, 9, 5),
    2025: date(2025, 9, 4),
    2026: date(2026, 9, 10),
}

REGULAR_SEASON_WEEKS = 18


def kickoff_for(season: int) -> date:
    if season in KICKOFFS:
        return KICKOFFS[season]
    # Fallback: the Thursday after the first Monday in September.
    d = date(season, 9, 1)
    while d.weekday() != 0:  # Monday
        d += timedelta(days=1)
    return d + timedelta(days=3)


def current_season(today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    # A season "belongs" to the calendar year it kicks off in, and runs
    # through the Super Bowl in February.
    return today.year if today.month >= 3 else today.year - 1


def current_week(season: int | None = None, today: date | None = None) -> int:
    """The week number outlets are labelling their newest rankings with.

    Outlets label by the *upcoming* week: the rankings that land on the
    Tuesday after Week 1's games are "Week 2 Power Rankings". Week N's games
    run Thursday (kickoff + 7(N-1)) through Monday (+4 days), so the label
    rolls over on the Tuesday at offset 5, 12, 19, ...
    """
    today = today or datetime.now(timezone.utc).date()
    season = season if season is not None else current_season(today)
    offset = (today - kickoff_for(season)).days
    if offset < 5:
        return 1  # preseason and Week 1 itself: outlets are on "Week 1"
    return max(1, min((offset - 5) // 7 + 2, REGULAR_SEASON_WEEKS))


def games_through(week: int) -> int:
    """Games completed at the time a given ranking week is published."""
    return max(0, week - 1)


def week_label(week: int) -> str:
    return f"Week {week}"
