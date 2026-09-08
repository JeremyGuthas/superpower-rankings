"""Outlets that keep their rankings on one permanent, server-rendered URL.

Nothing to discover — the page always shows the current week. An optional
`scope` regex narrows parsing to the ranking widget so that navigation and
"related teams" links can't poison the extraction.
"""
from __future__ import annotations

import html
import re

from .. import http
from .base import Article, Source, SourceFailure

TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
AUTHOR = re.compile(r'"author"\s*:\s*(?:\[)?\s*\{[^}]*?"name"\s*:\s*"([^"]+)"')
UPDATED = re.compile(r'"date(?:Modified|Published)"\s*:\s*"([^"]+)"')


class StaticPageSource(Source):
    def __init__(self, id: str, name: str, url: str, scope: str | None = None):
        self.id = id
        self.name = name
        self.homepage = url
        self.url = url
        self.scope = re.compile(scope, re.S) if scope else None

    def find_article(self, season: int, week: int) -> Article:
        return Article(url=self.url, title=f"{self.name} NFL Power Rankings")

    def load(self, article: Article) -> Article:
        page = http.get(self.url, cache_hours=3)
        if self.scope:
            m = self.scope.search(page)
            if not m:
                raise SourceFailure(f"{self.name}: rankings widget not found on page")
            article.markup = m.group(0)
        else:
            article.markup = page
        if t := TITLE.search(page):
            article.title = html.unescape(t.group(1)).split(" | ")[0].strip()
        if a := AUTHOR.search(page):
            article.author = html.unescape(a.group(1))
        if u := UPDATED.search(page):
            article.published = u.group(1)
        return article
