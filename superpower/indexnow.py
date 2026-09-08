"""Push changed URLs to the search engines that accept a push.

Google retired its sitemap ping in 2023 and only takes submissions through
Search Console, which needs an account. Bing, Yandex, Seznam and Naver all
accept IndexNow: host a file at /<key>.txt containing the key, then POST the
list of changed URLs. That is the whole protocol — no account, no dashboard.

Called from the Tuesday workflow after the site deploys.
"""
from __future__ import annotations

import logging
import re

import requests

from . import config

log = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10_000


def key_file_body() -> str:
    return config.INDEXNOW_KEY + "\n"


def submit(urls: list[str], *, timeout: int = 30) -> tuple[bool, str]:
    """Announce changed URLs. Returns (ok, message); never raises."""
    if not config.INDEXNOW_KEY:
        return False, "no IndexNow key configured"
    if not urls:
        return False, "nothing to submit"

    host = config.SITE_URL.split("//", 1)[-1].strip("/").split("/")[0]
    payload = {
        "host": host,
        "key": config.INDEXNOW_KEY,
        "keyLocation": config.url(f"{config.INDEXNOW_KEY}.txt"),
        "urlList": urls[:MAX_URLS],
    }
    try:
        response = requests.post(
            ENDPOINT, json=payload, timeout=timeout,
            headers={"User-Agent": f"{config.SITE_NAME} indexnow"})
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    # 200 accepted; 202 accepted with the key still being validated.
    return response.status_code in (200, 202), f"HTTP {response.status_code}"


def urls_from_sitemap_text(text: str) -> list[str]:
    return re.findall(r"<loc>([^<]+)</loc>", text)


def main() -> int:
    """CLI: read the live sitemap and announce every URL in it.

    Run after a deploy — reading the *published* sitemap doubles as a check
    that the deploy actually landed before we tell anyone to come and look.
    """
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--sitemap", default=config.url("sitemap.xml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        body = requests.get(args.sitemap, timeout=30).text
    except Exception as exc:
        log.error("could not read %s: %s", args.sitemap, exc)
        return 0  # never fail a deploy over a notification

    urls = urls_from_sitemap_text(body)
    log.info("%d urls in the published sitemap", len(urls))
    if args.dry_run:
        for u in urls[:5]:
            log.info("  %s", u)
        return 0

    ok, message = submit(urls)
    log.info("IndexNow: %s (%s)", "accepted" if ok else "not accepted", message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
