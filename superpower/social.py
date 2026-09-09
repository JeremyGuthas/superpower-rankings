"""Post the weekly board to whichever networks are configured.

Every adapter is off until its credentials exist and is skipped silently when
they do not. Nothing here ever raises: a network being down, rate-limited or
misconfigured must not fail the deploy that produced the rankings.

Credentials come from GitHub Actions secrets. They are never read from a file
in the repository and never logged, not even in part.

Reddit is handled differently on purpose — see `reddit_submission`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import config, sharekit

log = logging.getLogger(__name__)

TIMEOUT = 30
#: Which weeks have already been announced, so a re-run never double-posts.
LEDGER = Path(__file__).resolve().parent.parent / "data" / "promoted.json"


@dataclass
class Result:
    network: str
    ok: bool
    detail: str = ""
    url: str = ""
    skipped: bool = False


@dataclass
class Announcement:
    season: int
    week: int
    link: str
    texts: dict[str, str] = field(default_factory=dict)

    def text(self, network: str) -> str:
        return self.texts.get(network, self.texts.get("bluesky", ""))


def announcement(site: dict, week: dict) -> Announcement:
    networks = list(config.SOCIAL) + ["reddit"]
    return Announcement(
        season=site["season"],
        week=week["week"],
        link=config.url(f"{site['season']}/week-{week['week']}/"),
        texts={n: sharekit.platform_text(site, week, n) for n in networks},
    )


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------

def _load_ledger() -> dict:
    if not LEDGER.exists():
        return {}
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def already_posted(season: int, week: int, network: str) -> bool:
    return network in _load_ledger().get(f"{season}-{week:02d}", {})


def record(season: int, week: int, network: str, url: str = "") -> None:
    ledger = _load_ledger()
    key = f"{season}-{week:02d}"
    ledger.setdefault(key, {})[network] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": url,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------

def post_bluesky(text: str, link: str) -> Result:
    creds = config.SOCIAL["bluesky"]
    try:
        session = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": creds["handle"], "password": creds["app_password"]},
            timeout=TIMEOUT)
        session.raise_for_status()
        auth = session.json()

        # A link is only clickable on Bluesky if its byte range is declared.
        raw = text.encode("utf-8")
        start = raw.find(link.encode("utf-8"))
        facets = []
        if start >= 0:
            facets = [{
                "index": {"byteStart": start, "byteEnd": start + len(link.encode())},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
            }]

        created = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {auth['accessJwt']}"},
            json={"repo": auth["did"], "collection": "app.bsky.feed.post",
                  "record": {"$type": "app.bsky.feed.post", "text": text,
                             "facets": facets,
                             "createdAt": datetime.now(timezone.utc)
                             .isoformat(timespec="seconds").replace("+00:00", "Z")}},
            timeout=TIMEOUT)
        created.raise_for_status()
        return Result("bluesky", True, "posted", created.json().get("uri", ""))
    except Exception as exc:
        return Result("bluesky", False, f"{type(exc).__name__}: {exc}")


def post_x(text: str, link: str) -> Result:
    creds = config.SOCIAL["x"]
    try:
        from requests_oauthlib import OAuth1
        auth = OAuth1(creds["api_key"], creds["api_secret"],
                      creds["access_token"], creds["access_secret"])
        response = requests.post("https://api.twitter.com/2/tweets",
                                 auth=auth, json={"text": text}, timeout=TIMEOUT)
        if response.status_code >= 300:
            return Result("x", False, f"HTTP {response.status_code}: {response.text[:160]}")
        tweet_id = (response.json().get("data") or {}).get("id", "")
        return Result("x", True, "posted",
                      f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "")
    except Exception as exc:
        return Result("x", False, f"{type(exc).__name__}: {exc}")


def post_mastodon(text: str, link: str) -> Result:
    creds = config.SOCIAL["mastodon"]
    try:
        response = requests.post(
            creds["base_url"].rstrip("/") + "/api/v1/statuses",
            headers={"Authorization": f"Bearer {creds['token']}"},
            data={"status": text, "visibility": "public"}, timeout=TIMEOUT)
        response.raise_for_status()
        return Result("mastodon", True, "posted", response.json().get("url", ""))
    except Exception as exc:
        return Result("mastodon", False, f"{type(exc).__name__}: {exc}")


def post_facebook(text: str, link: str) -> Result:
    creds = config.SOCIAL["facebook"]
    try:
        response = requests.post(
            f"https://graph.facebook.com/v21.0/{creds['page_id']}/feed",
            data={"message": text, "link": link, "access_token": creds["token"]},
            timeout=TIMEOUT)
        if response.status_code >= 300:
            return Result("facebook", False,
                          f"HTTP {response.status_code}: {response.text[:160]}")
        return Result("facebook", True, "posted", response.json().get("id", ""))
    except Exception as exc:
        return Result("facebook", False, f"{type(exc).__name__}: {exc}")


def post_threads(text: str, link: str) -> Result:
    """Threads publishes in two steps: create a container, then publish it."""
    creds = config.SOCIAL["threads"]
    try:
        container = requests.post(
            f"https://graph.threads.net/v1.0/{creds['user_id']}/threads",
            data={"media_type": "TEXT", "text": text,
                  "access_token": creds["token"]}, timeout=TIMEOUT)
        if container.status_code >= 300:
            return Result("threads", False,
                          f"container HTTP {container.status_code}: {container.text[:140]}")
        published = requests.post(
            f"https://graph.threads.net/v1.0/{creds['user_id']}/threads_publish",
            data={"creation_id": container.json()["id"],
                  "access_token": creds["token"]}, timeout=TIMEOUT)
        if published.status_code >= 300:
            return Result("threads", False,
                          f"publish HTTP {published.status_code}: {published.text[:140]}")
        return Result("threads", True, "posted", published.json().get("id", ""))
    except Exception as exc:
        return Result("threads", False, f"{type(exc).__name__}: {exc}")


def post_discord(text: str, link: str) -> Result:
    try:
        response = requests.post(config.SOCIAL["discord"]["webhook"],
                                 json={"content": text}, timeout=TIMEOUT)
        if response.status_code >= 300:
            return Result("discord", False, f"HTTP {response.status_code}")
        return Result("discord", True, "posted")
    except Exception as exc:
        return Result("discord", False, f"{type(exc).__name__}: {exc}")


ADAPTERS = {
    "bluesky": post_bluesky,
    "x": post_x,
    "mastodon": post_mastodon,
    "facebook": post_facebook,
    "threads": post_threads,
    "discord": post_discord,
}


# --------------------------------------------------------------------------
# Reddit
#
# Reddit is the best early traffic source for this site and the easiest one to
# lose permanently. Most large subreddits treat an account that posts its own
# domain on a schedule as spam, and the penalty is a site-wide domain ban that
# no amount of good content undoes.
#
# So the default is to *prepare* the submission, not send it. Auto-posting is
# possible, but it has to be turned on deliberately.
# --------------------------------------------------------------------------

def reddit_submission(site: dict, week: dict) -> dict:
    """Title and body, ready to paste."""
    season = site["season"]
    return {
        "title": (f"[OC] {season} {week['label']} NFL Power Rankings — "
                  f"every major outlet averaged into one board"),
        "body": sharekit.build(site, week),
        "url": config.url(f"{season}/week-{week['week']}/"),
        "subreddits": config.REDDIT_SUBREDDITS,
    }


def _reddit_token() -> str:
    creds = config.SOCIAL["reddit"]
    response = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(creds["client_id"], creds["client_secret"]),
        data={"grant_type": "password", "username": creds["username"],
              "password": creds["password"]},
        headers={"User-Agent": creds["user_agent"]}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()["access_token"]


def post_reddit(site: dict, week: dict) -> list[Result]:
    if not config.REDDIT_AUTOPOST:
        return [Result("reddit", True, "draft written; auto-posting is off "
                                       "(set REDDIT_AUTOPOST=true to enable)",
                       skipped=True)]
    if not config.social_enabled("reddit") or not config.REDDIT_SUBREDDITS:
        return [Result("reddit", False, "not configured", skipped=True)]

    submission = reddit_submission(site, week)
    try:
        token = _reddit_token()
    except Exception as exc:
        return [Result("reddit", False, f"auth failed: {type(exc).__name__}: {exc}")]

    out = []
    for subreddit in config.REDDIT_SUBREDDITS:
        try:
            response = requests.post(
                "https://oauth.reddit.com/api/submit",
                headers={"Authorization": f"Bearer {token}",
                         "User-Agent": config.SOCIAL["reddit"]["user_agent"]},
                data={"sr": subreddit, "kind": "self", "title": submission["title"],
                      "text": submission["body"], "api_type": "json"},
                timeout=TIMEOUT)
            payload = response.json() if response.ok else {}
            errors = (payload.get("json") or {}).get("errors") or []
            if errors:
                out.append(Result(f"reddit:{subreddit}", False, str(errors[:1])))
            else:
                link = ((payload.get("json") or {}).get("data") or {}).get("url", "")
                out.append(Result(f"reddit:{subreddit}", True, "submitted", link))
        except Exception as exc:
            out.append(Result(f"reddit:{subreddit}", False,
                              f"{type(exc).__name__}: {exc}"))
    return out


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def publish(site: dict, week: dict, *, dry_run: bool = False,
            force: bool = False) -> list[Result]:
    note = announcement(site, week)
    season, number = site["season"], week["week"]
    results: list[Result] = []

    for network, adapter in ADAPTERS.items():
        if not config.social_enabled(network):
            results.append(Result(network, True, "not configured", skipped=True))
            continue
        if not force and already_posted(season, number, network):
            results.append(Result(network, True, "already posted this week",
                                  skipped=True))
            continue
        text = note.text(network)
        if dry_run:
            results.append(Result(network, True,
                                  f"would post {len(text)} chars", skipped=True))
            continue
        outcome = adapter(text, note.link)
        if outcome.ok:
            record(season, number, network, outcome.url)
        results.append(outcome)

    if dry_run:
        results.append(Result("reddit", True, "would write a draft", skipped=True))
    else:
        results.extend(post_reddit(site, week))
    return results


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Announce the latest week.")
    parser.add_argument("--season", type=int)
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be sent, send nothing")
    parser.add_argument("--force", action="store_true",
                        help="post again even if this week was already announced")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from . import season as season_mod
    from . import store

    season = args.season or season_mod.current_season()
    site_file = store.DATA / f"season-{season}.json"
    if not site_file.exists():
        log.error("no data for %s", season)
        return 0
    site = json.loads(site_file.read_text(encoding="utf-8"))
    if not site["weeks"]:
        log.error("no weeks stored for %s", season)
        return 0
    week = max(site["weeks"], key=lambda w: w["week"])

    for result in publish(site, week, dry_run=args.dry_run, force=args.force):
        state = "skip" if result.skipped else ("ok" if result.ok else "FAIL")
        log.info("%-18s %-5s %s %s", result.network, state, result.detail, result.url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
