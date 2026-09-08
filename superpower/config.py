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


# --------------------------------------------------------------------------
# Monetisation.
#
# Every surface below is off until it is configured, and renders *nothing*
# when off — no empty boxes, no placeholder text, no third-party scripts.
# The page you see today is the page a reader sees; each slot fills in only
# once the corresponding account exists.
# --------------------------------------------------------------------------

#: Google AdSense publisher id, e.g. "ca-pub-1234567890123456".
#: Until this is set no ad markup and no ad script reach the page at all.
AD_CLIENT = os.environ.get("AD_CLIENT", "")

#: Slot ids from the AdSense dashboard. A slot with no id is skipped.
AD_SLOTS = {
    "board_leader": os.environ.get("AD_SLOT_BOARD", ""),
    "in_content": os.environ.get("AD_SLOT_CONTENT", ""),
    "team_side": os.environ.get("AD_SLOT_TEAM", ""),
}

#: Form endpoint for the newsletter (Buttondown, beehiiv, ConvertKit, Mailchimp
#: all give you one). Empty hides every signup form on the site.
NEWSLETTER_ACTION = os.environ.get("NEWSLETTER_ACTION", "")
NEWSLETTER_NOTE = "The weekly board and the week's arguments, every Tuesday."

#: Sportsbook affiliate links, {label: url}. Empty means no betting CTAs,
#: no age gate and no responsible-gambling furniture anywhere on the site.
#: Do not populate this until you are registered in the states you promote in.
AFFILIATE_BOOKS: dict[str, str] = {}

#: Shown beside anything that could be read as a betting recommendation.
RESPONSIBLE_GAMBLING = (
    "21+ and present in a state where betting is legal. "
    "If gambling is a problem, call 1-800-GAMBLER."
)

CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")

#: IndexNow key. Bing, Yandex, Seznam and Naver accept a push the moment a
#: page changes, and the only proof of ownership is a file at /<key>.txt
#: containing the key — no account, no console, no waiting. Google does not
#: participate; it has to be told through Search Console instead.
INDEXNOW_KEY = "45a995356c0b45b8bff3859f739f8a7e"

#: Search-console ownership tokens. Each renders a verification <meta> when set.
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
BING_SITE_VERIFICATION = os.environ.get("BING_SITE_VERIFICATION", "")

#: Cloudflare Web Analytics token — cookie-free, so it needs no consent banner.
CF_ANALYTICS_TOKEN = os.environ.get("CF_ANALYTICS_TOKEN", "")

#: Publisher ids for ads.txt. AdSense will not serve without this file once
#: your account exists; sellers.json/ads.txt is how a buyer confirms the
#: inventory is really yours.
def ads_txt() -> str:
    if not AD_CLIENT:
        return ""
    pub = AD_CLIENT.replace("ca-pub-", "")
    return f"google.com, pub-{pub}, DIRECT, f08c47fec0942fa0\n"


def ads_enabled() -> bool:
    return bool(AD_CLIENT)


def newsletter_enabled() -> bool:
    return bool(NEWSLETTER_ACTION)


def affiliates_enabled() -> bool:
    return bool(AFFILIATE_BOOKS)


def url(path: str = "") -> str:
    """Absolute URL for a site-relative path."""
    return SITE_URL.rstrip("/") + "/" + path.lstrip("/")


def is_placeholder() -> bool:
    """True while the site is still on a github.io URL rather than a domain."""
    return "github.io" in SITE_URL
