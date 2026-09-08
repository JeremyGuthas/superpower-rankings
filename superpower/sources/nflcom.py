"""NFL.com — Around The NFL weekly power rankings.

The /news/series/ index is client-rendered and useless to a script, but the
homepage and /news/ are server-rendered and always surface the current
week's rankings while they are the fresh piece.
"""
from __future__ import annotations

import html
import re

from .. import http
from .base import Article, Source, SourceFailure, looks_like_weekly

POOLS = ("https://www.nfl.com/", "https://www.nfl.com/news/")
LINK = re.compile(r'href="(https://www\.nfl\.com/news/[a-z0-9-]+)"')
TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
AUTHOR = re.compile(r'"author"\s*:\s*(?:\[)?\s*\{[^}]*?"name"\s*:\s*"([^"]+)"')
PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')


class NFLcom(Source):
    id = "nfl"
    name = "NFL.com"
    homepage = "https://www.nfl.com/news/"

    def find_article(self, season: int, week: int) -> Article:
        seen: list[str] = []
        for pool in POOLS:
            try:
                page = http.get(pool, cache_hours=1)
            except Exception:
                continue
            for url in LINK.findall(page):
                slug = url.rsplit("/", 1)[-1]
                if looks_like_weekly(slug) and url not in seen:
                    seen.append(url)
        if not seen:
            raise SourceFailure("no NFL.com power rankings article found")
        # Prefer a slug that names the current week, else the first (newest) hit.
        for url in seen:
            if f"week-{week}" in url and not re.search(rf"week-{week}\d", url):
                return Article(url=url)
        return Article(url=seen[0])

    def load(self, article: Article) -> Article:
        page = http.get(article.url, cache_hours=3)
        article.markup = page
        if m := TITLE.search(page):
            article.title = html.unescape(m.group(1)).split(" | ")[0].strip()
        if m := AUTHOR.search(page):
            article.author = html.unescape(m.group(1))
        if m := PUBLISHED.search(page):
            article.published = m.group(1)
        return article
