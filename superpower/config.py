"""Site-wide settings.

The public URL is the one value that has to agree everywhere — canonical
tags, the sitemap, Open Graph share links, the CNAME file GitHub Pages
reads, and the links inside the email digest. It lives here so changing
domains is a one-line edit, and can be overridden per-run with the
SITE_URL environment variable (which is what CI does).
"""
from __future__ import annotations

import os

#: The domain the site is served from. Set this once you own it.
#: Until then the free GitHub Pages URL works and everything still builds.
DOMAIN = "superpowerrankings.com"

#: Serve the apex, with www redirecting to it (configured at the registrar).
SITE_URL = os.environ.get("SITE_URL") or f"https://{DOMAIN}/"

SITE_NAME = "Superpower Rankings"
TAGLINE = "Every major NFL power ranking, averaged into one board."


def url(path: str = "") -> str:
    """Absolute URL for a site-relative path."""
    return SITE_URL.rstrip("/") + "/" + path.lstrip("/")


def is_placeholder() -> bool:
    """True while the site is still on a github.io URL rather than a domain."""
    return "github.io" in SITE_URL
