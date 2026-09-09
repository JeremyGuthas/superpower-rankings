"""A configurable source for outlets that publish an ordinary article.

Discovery walks one or more server-rendered listing pages (or RSS feeds),
keeps links whose slug or title reads like a weekly power rankings piece,
and hands the newest one to the shared extractor. Any outlet the generic
path cannot handle simply fails for the week and is left out of the average.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

from .. import http
from .base import Article, Source, SourceFailure, looks_like_weekly

#: How many discovered articles to try before giving up on a source.
MAX_CANDIDATES = 4

TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
AUTHOR = re.compile(r'"author"\s*:\s*(?:\[)?\s*\{[^}]*?"name"\s*:\s*"([^"]+)"')
PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')


class GenericSource(Source):
    supports_history = False  # listings only ever surface recent articles

    def __init__(self, id: str, name: str, listings: tuple[str, ...],
                 link_pattern: str, homepage: str = "", feeds: tuple[str, ...] = ()):
        self.id = id
        self.name = name
        self.homepage = homepage or (listings[0] if listings else "")
        self.listings = listings
        self.feeds = feeds
        self.link_re = re.compile(link_pattern)

    # -- discovery ----------------------------------------------------------

    def _from_feeds(self) -> list[Article]:
        found = []
        for feed in self.feeds:
            try:
                root = ET.fromstring(http.get(feed, cache_hours=1).encode("utf-8"))
            except Exception:
                continue
            for item in root.iter():
                if not item.tag.endswith("item") and not item.tag.endswith("entry"):
                    continue
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                date = (item.findtext("pubDate") or item.findtext("published") or "").strip()
                if link and looks_like_weekly(title):
                    found.append(Article(url=link, title=title, published=date))
        return found

    def _from_listings(self) -> list[Article]:
        found, seen = [], set()
        for listing in self.listings:
            try:
                page = http.get(listing, cache_hours=1)
            except Exception:
                continue
            base = "/".join(listing.split("/")[:3])
            for m in self.link_re.finditer(page):
                url = next((g for g in m.groups() if g), None) if m.groups() else m.group(0)
                if not url:
                    continue
                if url.startswith("/"):
                    url = base + url
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                if url not in seen and looks_like_weekly(slug):
                    seen.add(url)
                    found.append(Article(url=url))
        return found

    def candidates(self, season: int, week: int) -> list[Article]:
        found = self._from_feeds() + self._from_listings()
        if not found:
            raise SourceFailure(f"no {self.name} power rankings article found")
        # An article naming this week is the best guess, but only a guess.
        named = [a for a in found
                 if re.search(rf"week[-\s]?{week}(?!\d)", a.url + " " + a.title, re.I)]
        rest = [a for a in found if a not in named]
        return (named + rest)[:MAX_CANDIDATES]

    def find_article(self, season: int, week: int) -> Article:
        return self.candidates(season, week)[0]

    # -- loading ------------------------------------------------------------

    def load(self, article: Article) -> Article:
        page = http.get(article.url, cache_hours=3)
        article.markup = page
        if not article.title and (m := TITLE.search(page)):
            article.title = html.unescape(m.group(1)).split(" | ")[0].strip()
        if m := AUTHOR.search(page):
            article.author = html.unescape(m.group(1))
        if m := PUBLISHED.search(page):
            article.published = m.group(1)
        return article
