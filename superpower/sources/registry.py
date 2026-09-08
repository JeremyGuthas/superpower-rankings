"""Every outlet the aggregator knows about.

Adding an outlet is a one-line entry here. Sources that fail for a given
week are recorded and skipped, never guessed at.
"""
from __future__ import annotations

from .espn import ESPN
from .generic import GenericSource
from .nflcom import NFLcom
from .static_page import StaticPageSource

SOURCES = [
    ESPN(),
    NFLcom(),
    StaticPageSource(
        id="cbs", name="CBS Sports",
        url="https://www.cbssports.com/nfl/powerrankings/",
        scope=r"table-power-rankings.*?</table>",
    ),
    StaticPageSource(
        id="sharpfootball", name="Sharp Football Analysis",
        url="https://www.sharpfootballanalysis.com/analysis/nfl-power-rankings/",
    ),
    GenericSource(
        id="yahoo", name="Yahoo Sports",
        homepage="https://sports.yahoo.com/nfl/",
        listings=("https://sports.yahoo.com/nfl/",),
        feeds=("https://sports.yahoo.com/nfl/rss.xml",),
        link_pattern=r'href="(https://sports\.yahoo\.com/[^"]*?power-rankings[^"]*?)"'
                     r'|href="(/article/[^"]*power-rankings[^"]*)"',
    ),
    GenericSource(
        id="sportingnews", name="Sporting News",
        homepage="https://www.sportingnews.com/us/nfl",
        listings=("https://www.sportingnews.com/us/nfl",),
        feeds=("https://www.sportingnews.com/us/rss",),
        link_pattern=r'href="(https://www\.sportingnews\.com/us/nfl/news/[^"]*power-rankings[^"]*)"',
    ),
    GenericSource(
        id="foxsports", name="FOX Sports",
        homepage="https://www.foxsports.com/nfl",
        listings=("https://www.foxsports.com/nfl",),
        feeds=("https://api.foxsports.com/v1/rss?tag=nfl",),
        link_pattern=r'href="(https://www\.foxsports\.com/stories/nfl/[^"]*power-rankings[^"]*)"',
    ),
    GenericSource(
        id="bleacherreport", name="Bleacher Report",
        homepage="https://bleacherreport.com/nfl",
        listings=("https://bleacherreport.com/nfl",),
        link_pattern=r'href="(/articles/[^"]*power-rankings[^"]*)"',
    ),
]

BY_ID = {s.id: s for s in SOURCES}


def enabled_sources(only: list[str] | None = None, exclude: list[str] | None = None):
    picked = [BY_ID[i] for i in only] if only else list(SOURCES)
    if exclude:
        picked = [s for s in picked if s.id not in exclude]
    return picked
