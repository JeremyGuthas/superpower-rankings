"""ESPN.

www.espn.com is behind a bot wall for scripted clients, but two ESPN JSON
hosts are not, and between them they give a cleaner result than scraping the
page ever would:

  site.web.api.espn.com/apis/search/v2  -> finds the article, its date and URL
  now.core.api.espn.com/v1/sports/news  -> returns the full story body

The search index also reaches back through past seasons, which is what makes
`backfill` possible for this source.
"""
from __future__ import annotations

import re

from .. import http
from .base import Article, Source, SourceFailure, looks_like_weekly

SEARCH = ("https://site.web.api.espn.com/apis/search/v2"
          "?region=us&lang=en&section=nfl&limit=50&page={page}&query=NFL%20power%20rankings")
STORY = "https://now.core.api.espn.com/v1/sports/news/{id}?enable=story"


def _candidates(pages: int = 2) -> list[Article]:
    out: list[Article] = []
    for page in range(1, pages + 1):
        try:
            data = http.get_json(SEARCH.format(page=page), cache_hours=1)
        except Exception:
            break
        for group in data.get("results", []):
            if group.get("type") != "article":
                continue
            for item in group.get("contents", []):
                link = (item.get("link") or {}).get("web", "")
                # The same search index also serves MLS, NWSL, MLB and college
                # power rankings; the URL section is the only reliable filter.
                if "/nfl/story/" not in link:
                    continue
                title = item.get("displayName", "")
                if not looks_like_weekly(title) and not looks_like_weekly(link):
                    continue
                out.append(Article(url=link, title=title,
                                   published=item.get("date", "")))
    return out


class ESPN(Source):
    id = "espn"
    name = "ESPN"
    homepage = "https://www.espn.com/nfl/"
    supports_history = True

    def find_article(self, season: int, week: int) -> Article:
        cands = _candidates()
        if not cands:
            raise SourceFailure("no ESPN power rankings article found")

        # ESPN slugs the weekly piece "nfl-week-N-power-rankings-<season>".
        exact = [a for a in cands
                 if re.search(rf"week-{week}(?!\d)", a.url, re.I)
                 and str(season) in (a.url + a.published)]
        if exact:
            return max(exact, key=lambda a: a.published)

        # Week 1 rankings are published as the preseason edition.
        if week == 1:
            pre = [a for a in cands
                   if "preseason" in (a.url + a.title).lower()
                   and str(season) in (a.url + a.title + a.published)]
            if pre:
                return max(pre, key=lambda a: a.published)

        in_season = [a for a in cands if str(season) in (a.url + a.published)]
        if not in_season:
            raise SourceFailure(f"no ESPN rankings found for {season} week {week}")
        return max(in_season, key=lambda a: a.published)

    def load(self, article: Article) -> Article:
        m = re.search(r"/id/(\d+)", article.url)
        if not m:
            raise SourceFailure(f"unrecognised ESPN url: {article.url}")
        data = http.get_json(STORY.format(id=m.group(1)), cache_hours=3)
        head = data["headlines"][0]
        article.markup = head.get("story", "")
        article.title = head.get("title") or article.title
        article.published = head.get("published") or article.published
        article.author = re.sub(r"^by\s+", "",
                                head.get("byline") or "", flags=re.I).strip()
        if not article.markup:
            raise SourceFailure("ESPN story body was empty")
        return article

    def known_weeks(self, season: int) -> dict[int, Article]:
        """Weeks ESPN's search index can still reach, for backfilling."""
        found: dict[int, Article] = {}
        for art in _candidates(pages=3):
            if str(season) not in (art.url + art.published):
                continue
            if m := re.search(r"week-(\d{1,2})(?!\d)", art.url, re.I):
                found.setdefault(int(m.group(1)), art)
            elif "preseason" in (art.url + art.title).lower():
                found.setdefault(1, art)
        return found
