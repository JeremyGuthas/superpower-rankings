"""Tests for distribution.

The rules that matter here are about restraint: nothing posts without
credentials, nothing posts twice, and Reddit does not post itself.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from superpower import config, sharekit, social  # noqa: E402


@pytest.fixture
def site():
    return json.loads((ROOT / "data" / "season-2026.json").read_text())


@pytest.fixture
def week(site):
    return max(site["weeks"], key=lambda w: w["week"])


@pytest.fixture(autouse=True)
def ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "LEDGER", tmp_path / "promoted.json")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("a test tried to reach the network")
    monkeypatch.setattr(social.requests, "post", forbidden)
    monkeypatch.setattr(social.requests, "get", forbidden)


# --------------------------------------------------------- copy fits

@pytest.mark.parametrize("network,limit", sorted(sharekit.LIMITS.items()))
def test_copy_fits_every_network_limit(site, week, network, limit):
    text = sharekit.platform_text(site, week, network)
    assert 0 < len(text) <= limit, f"{network}: {len(text)} chars"


def test_copy_always_carries_the_link(site, week):
    for network in sharekit.LIMITS:
        assert config.url("") in sharekit.platform_text(site, week, network)


def test_short_networks_get_shorter_copy(site, week):
    assert (len(sharekit.platform_text(site, week, "x"))
            <= len(sharekit.platform_text(site, week, "facebook")))


# --------------------------------------------------- nothing posts unasked

def test_nothing_posts_without_credentials(site, week):
    results = social.publish(site, week)
    assert all(r.skipped for r in results)
    assert all(r.ok for r in results)


def test_dry_run_sends_nothing(site, week, monkeypatch):
    monkeypatch.setitem(config.SOCIAL, "bluesky",
                        {"handle": "a.bsky.social", "app_password": "x"})
    results = social.publish(site, week, dry_run=True)
    # The autouse no_network fixture would have raised on any real call.
    assert any(r.network == "bluesky" and r.skipped for r in results)


def test_a_week_is_not_announced_twice(site, week, monkeypatch):
    monkeypatch.setitem(config.SOCIAL, "bluesky",
                        {"handle": "a.bsky.social", "app_password": "x"})
    sent = []

    def fake(text, link):
        sent.append(text)
        return social.Result("bluesky", True, "posted", "at://x")

    monkeypatch.setitem(social.ADAPTERS, "bluesky", fake)
    social.publish(site, week)
    social.publish(site, week)
    assert len(sent) == 1


def test_force_reposts(site, week, monkeypatch):
    monkeypatch.setitem(config.SOCIAL, "bluesky",
                        {"handle": "a.bsky.social", "app_password": "x"})
    sent = []
    monkeypatch.setitem(social.ADAPTERS, "bluesky",
                        lambda t, l: (sent.append(t),
                                      social.Result("bluesky", True, "posted"))[1])
    social.publish(site, week)
    social.publish(site, week, force=True)
    assert len(sent) == 2


def test_a_failed_post_is_not_recorded(site, week, monkeypatch):
    monkeypatch.setitem(config.SOCIAL, "bluesky",
                        {"handle": "a.bsky.social", "app_password": "x"})
    monkeypatch.setitem(social.ADAPTERS, "bluesky",
                        lambda t, l: social.Result("bluesky", False, "boom"))
    social.publish(site, week)
    assert not social.already_posted(site["season"], week["week"], "bluesky")


def test_one_network_failing_does_not_stop_the_others(site, week, monkeypatch):
    for name in ("bluesky", "mastodon"):
        monkeypatch.setitem(config.SOCIAL, name, {"a": "1", "b": "2"})
    monkeypatch.setitem(social.ADAPTERS, "bluesky",
                        lambda t, l: social.Result("bluesky", False, "boom"))
    monkeypatch.setitem(social.ADAPTERS, "mastodon",
                        lambda t, l: social.Result("mastodon", True, "posted"))
    results = {r.network: r for r in social.publish(site, week)}
    assert results["bluesky"].ok is False
    assert results["mastodon"].ok is True


# ------------------------------------------------------------- reddit

def test_reddit_does_not_post_itself_by_default(site, week, monkeypatch):
    monkeypatch.setattr(config, "REDDIT_AUTOPOST", False)
    monkeypatch.setitem(config.SOCIAL, "reddit",
                        {"client_id": "a", "client_secret": "b", "username": "c",
                         "password": "d", "user_agent": "e"})
    monkeypatch.setattr(config, "REDDIT_SUBREDDITS", ["nfl"])
    results = social.post_reddit(site, week)
    # The no_network fixture guarantees nothing was sent.
    assert len(results) == 1 and results[0].skipped
    assert "auto-posting is off" in results[0].detail


def test_reddit_submission_is_ready_to_paste(site, week):
    submission = social.reddit_submission(site, week)
    assert submission["title"].startswith("[OC]")
    assert str(site["season"]) in submission["title"]
    assert submission["url"] in submission["body"]
    assert "Top 10:" in submission["body"]
