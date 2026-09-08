from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    url: str
    title: str = ""
    author: str = ""
    published: str = ""          # ISO-8601
    markup: str = ""             # raw HTML/story body, filled by the source


@dataclass
class SourceResult:
    source_id: str
    source_name: str
    article: Article
    ranks: dict[str, int]
    strategy: str
    fetched: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")


class SourceFailure(RuntimeError):
    """Raised when a source cannot be resolved for a given week."""


# Slugs that contain "power rankings" but are not the weekly 1-32 list.
OFFSEASON_SLUG_TOKENS = (
    "division", "future", "offseason", "free-agency", "draft", "mock",
    "position", "quarterback", "coach", "roster", "fantasy", "college",
    "nwsl", "mls", "nba", "mlb", "nhl", "wnba", "soccer", "champions-league",
    "premier-league", "ncaa", "cfb", "womens", "top-25", "way-too-early",
)


def looks_like_weekly(slug_or_title: str) -> bool:
    # Normalise separators so "Champions League" and "champions-league"
    # both trip the same exclusion token.
    s = re.sub(r"[^a-z0-9]+", "-", slug_or_title.lower())
    if "power" not in s or "rank" not in s:
        return False
    return not any(tok in s for tok in OFFSEASON_SLUG_TOKENS)


class Source:
    """Base class: find this week's article, then hand back its markup."""

    id: str = ""
    name: str = ""
    homepage: str = ""

    #: True only when the source can address a *specific past* week. A source
    #: that publishes to one permanent URL always shows the current rankings,
    #: so using it to backfill week 6 would silently file today's list under
    #: an old week. Those sources are skipped for anything but the live week.
    supports_history: bool = False

    def find_article(self, season: int, week: int) -> Article:
        raise NotImplementedError

    def load(self, article: Article) -> Article:
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source {self.id}>"
