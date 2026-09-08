"""Tests for the parts of the published site that are easy to break silently:
the monetisation gates, the SEO furniture, and the pre-rendered markup.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import prerender  # noqa: E402
from superpower import config  # noqa: E402


@pytest.fixture
def week():
    data = json.loads((ROOT / "data" / "season-2026.json").read_text())
    data["sourcesBy"] = {s["id"]: s["name"] for s in data["sources"]}
    return data, data["weeks"][0]


# ------------------------------------------------- monetisation is opt-in

def test_no_monetisation_markup_when_unconfigured(monkeypatch):
    monkeypatch.setattr(config, "AD_CLIENT", "")
    monkeypatch.setattr(config, "NEWSLETTER_ACTION", "")
    monkeypatch.setattr(config, "AFFILIATE_BOOKS", {})
    assert prerender.ad_slot("board_leader") == ""
    assert prerender.ad_head() == ""
    assert prerender.newsletter() == ""
    assert prerender.affiliate_block() == ""


def test_ad_slot_needs_both_client_and_slot_id(monkeypatch):
    monkeypatch.setattr(config, "AD_CLIENT", "ca-pub-123")
    monkeypatch.setattr(config, "AD_SLOTS", {"board_leader": ""})
    assert prerender.ad_slot("board_leader") == ""
    monkeypatch.setattr(config, "AD_SLOTS", {"board_leader": "999"})
    assert "adsbygoogle" in prerender.ad_slot("board_leader")


def test_ads_are_labelled_as_advertising(monkeypatch):
    monkeypatch.setattr(config, "AD_CLIENT", "ca-pub-123")
    monkeypatch.setattr(config, "AD_SLOTS", {"board_leader": "999"})
    html = prerender.ad_slot("board_leader")
    assert "Advertisement" in html and 'aria-label' in html


def test_affiliate_links_carry_sponsored_and_responsible_gambling(monkeypatch):
    monkeypatch.setattr(config, "AFFILIATE_BOOKS", {"Book": "https://example.com"})
    html = prerender.affiliate_block()
    # Undisclosed paid links are both an FTC problem and a Google policy one.
    assert 'rel="sponsored nofollow noopener"' in html
    assert "1-800-GAMBLER" in html
    assert "paid partnerships" in html


def test_outbound_source_links_are_nofollow(week):
    _, w = week
    html = prerender.sources_html(w)
    assert html.count('rel="noopener nofollow"') == len(w["sources"])


# ------------------------------------------------------------ SEO markup

def test_head_has_the_tags_a_crawler_needs():
    doc = prerender.set_head(
        "<html><head><title>x</title></head><body></body></html>",
        title="T", description="D", canonical="https://example.com/",
        og_image_url="https://example.com/og.png",
        jsonld=[{"@type": "WebSite"}])
    for needle in ('<title>T</title>', 'name="description" content="D"',
                   'rel="canonical" href="https://example.com/"',
                   'property="og:image"', 'name="twitter:card"',
                   'application/ld+json', 'type="application/rss+xml"'):
        assert needle in doc, needle


def test_head_replaces_rather_than_duplicates_description():
    doc = ('<html><head><title>x</title>'
           '<meta name="description" content="old"></head><body></body></html>')
    out = prerender.set_head(doc, title="T", description="new",
                             canonical="https://e.com/", og_image_url="https://e.com/o.png")
    assert out.count('name="description"') == 1
    assert "old" not in out


def test_fill_replaces_placeholder_content():
    doc = '<h1 id="boardTitle">Superpower Rankings</h1>'
    out = prerender.fill(doc, "boardTitle", "2026 Week 1")
    assert out == '<h1 id="boardTitle">2026 Week 1</h1>'


def test_fill_is_a_noop_for_an_unknown_id():
    doc = "<div>untouched</div>"
    assert prerender.fill(doc, "nope", "x") == doc


def test_rewrite_links_walks_up_to_the_asset_root():
    doc = '<link href="assets/style.css"><a href="compare.html">c</a>'
    out = prerender.rewrite_links(doc, 2)
    assert 'href="../../assets/style.css"' in out
    assert 'href="../../compare/"' in out


def test_page_state_is_injected_for_the_scripts():
    out = prerender.set_page_state("<head></head>", {"view": "team", "team": "KC"})
    assert "window.__PAGE__=" in out and '"team":"KC"' in out


# --------------------------------------------------------- rendered rows

def test_board_renders_every_team_with_a_crawlable_link(week):
    _, w = week
    head, rows = prerender.board_rows(w, depth=2)
    assert rows.count("<tr>") == 32
    # Each team must be a real href, not a JS-only click target.
    assert rows.count('href="../../teams/') == 32
    assert head.count("<th") == 7 + len(w["sources"])


def test_board_rows_are_in_rank_order(week):
    _, w = week
    _, rows = prerender.board_rows(w, depth=0)
    ranks = [int(m) for m in re.findall(r'<td class="l rk">(\d+)</td>', rows)]
    assert ranks == list(range(1, 33))


def test_movement_markup_distinguishes_up_down_and_new():
    assert "up" in prerender.movement_html(3)
    assert "down" in prerender.movement_html(-3)
    assert "flat" in prerender.movement_html(0)
    assert "NEW" in prerender.movement_html(None)


def test_chip_carries_the_team_name_for_screen_readers():
    html = prerender.chip_html("KC", 26)
    assert 'title="Kansas City Chiefs"' in html and ">KC<" in html


def test_no_hotlinked_logos_anywhere_in_rendered_markup(week):
    data, w = week
    _, rows = prerender.board_rows(w, 0)
    blob = rows + prerender.tiles_html(w, 0) + "".join(prerender.lanes_html(w, 0).values())
    assert "espncdn" not in blob and "<img" not in blob
