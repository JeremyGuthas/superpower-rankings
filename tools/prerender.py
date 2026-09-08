#!/usr/bin/env python3
"""Turn the single-page app into a site a search engine can actually read.

The pages are interactive and build themselves from JSON, which is fine for a
reader and useless for a crawler: one URL, no content in the HTML. This walks
the stored archive and writes a real page for every week and every team, with
the rankings already in the markup, a unique title and description, a canonical
URL, share cards, and structured data.

The JavaScript still runs and takes over for interaction — it re-renders the
same content it finds, so nothing on screen changes.

    python tools/prerender.py            # writes into _site/
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from superpower import config, og_image  # noqa: E402
from superpower.teams import info  # noqa: E402

OUT = ROOT / "_site"
TEMPLATES = ROOT / "site"

E = html.escape


# --------------------------------------------------------------------------
# template surgery
# --------------------------------------------------------------------------

def fill(doc: str, element_id: str, inner: str) -> str:
    """Replace the contents of the element carrying `id="element_id"`.

    The fill targets are all leaf containers in the templates — empty, or
    holding placeholder text — so matching the first closing tag is safe.
    """
    i = doc.find(f'id="{element_id}"')
    if i == -1:
        return doc
    open_start = doc.rfind("<", 0, i)
    tag = re.match(r"<([a-zA-Z][\w-]*)", doc[open_start:])
    if not tag:
        return doc
    body_start = doc.find(">", i)
    body_end = doc.find(f"</{tag.group(1)}", body_start)
    if body_start == -1 or body_end == -1:
        return doc
    return doc[:body_start + 1] + inner + doc[body_end:]


def set_head(doc: str, *, title: str, description: str, canonical: str,
             og_image_url: str, og_type: str = "website",
             jsonld: list[dict] | None = None, extra: str = "") -> str:
    doc = re.sub(r"<title>.*?</title>", f"<title>{E(title)}</title>", doc, count=1, flags=re.S)
    doc = re.sub(r'<meta name="description"[^>]*>\s*', "", doc, count=1)

    tags = [
        f'<meta name="description" content="{E(description)}">',
        f'<link rel="canonical" href="{E(canonical)}">',
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:site_name" content="{E(config.SITE_NAME)}">',
        f'<meta property="og:title" content="{E(title)}">',
        f'<meta property="og:description" content="{E(description)}">',
        f'<meta property="og:url" content="{E(canonical)}">',
        f'<meta property="og:image" content="{E(og_image_url)}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{E(title)}">',
        f'<meta name="twitter:description" content="{E(description)}">',
        f'<meta name="twitter:image" content="{E(og_image_url)}">',
        '<meta name="robots" content="index,follow,max-image-preview:large">',
        f'<link rel="alternate" type="application/rss+xml" title="{E(config.SITE_NAME)}" '
        f'href="{E(config.url("feed.xml"))}">',
    ]
    if config.GOOGLE_SITE_VERIFICATION:
        tags.append('<meta name="google-site-verification" content="'
                    f'{E(config.GOOGLE_SITE_VERIFICATION)}">')
    if config.BING_SITE_VERIFICATION:
        tags.append(f'<meta name="msvalidate.01" content="{E(config.BING_SITE_VERIFICATION)}">')
    if config.CF_ANALYTICS_TOKEN:
        # Cloudflare's own snippet, verbatim apart from the token. Modules are
        # deferred by default, so this costs nothing on first paint.
        tags.append('<script type="module" '
                    'src="https://static.cloudflareinsights.com/beacon.min.js" '
                    'data-cf-beacon=\'{"token": "' + E(config.CF_ANALYTICS_TOKEN)
                    + '"}\'></script>')
    for block in (jsonld or []):
        tags.append('<script type="application/ld+json">'
                    + json.dumps(block, separators=(",", ":")) + "</script>")
    if extra:
        tags.append(extra)
    return doc.replace("</head>", "\n".join(tags) + "\n</head>", 1)


def set_page_state(doc: str, state: dict) -> str:
    """Hand the scripts their starting state so clean URLs work without query strings."""
    return doc.replace(
        "</head>",
        "<script>window.__PAGE__=" + json.dumps(state, separators=(",", ":"))
        + ";</script>\n</head>", 1)


def rewrite_links(doc: str, depth: int) -> str:
    """Point the shell's asset and nav links at the clean URL structure."""
    up = "../" * depth
    doc = re.sub(r'(?P<a>src|href)="(?:\./)?assets/', lambda m: f'{m.group("a")}="{up}assets/', doc)
    for page, target in (("index.html", ""), ("compare.html", "compare/"),
                         ("accuracy.html", "accuracy/")):
        doc = doc.replace(f'href="{page}"', f'href="{up}{target}"')
    return doc


# --------------------------------------------------------------------------
# fragments — same class names the scripts emit, so nothing shifts on hydration
# --------------------------------------------------------------------------

def chip_html(abbr: str, size: int = 26) -> str:
    t = info(abbr)
    style = (f"background:{t['primary']};box-shadow:inset 0 0 0 1.5px {t['secondary']};"
             f"width:{size}px;height:{size}px;flex-basis:{size}px;"
             f"font-size:{max(7, round(size * 0.33))}px")
    return f'<span class="chip" style="{style}" title="{E(t["name"])}">{E(abbr)}</span>'


def team_link(abbr: str, depth: int, division: bool = True) -> str:
    t = info(abbr)
    up = "../" * depth
    div = f' <span class="div">{E(t["division"])}</span>' if division else ""
    return (f'<a class="team" href="{up}teams/{t["slug"]}/">{chip_html(abbr)}'
            f'<span><span class="nm">{E(t["name"])}</span>{div}</span></a>')


def movement_html(delta) -> str:
    if delta is None:
        return '<span class="mv new">NEW</span>'
    if delta > 0:
        return f'<span class="mv up">&#9650; {delta}</span>'
    if delta < 0:
        return f'<span class="mv down">&#9660; {abs(delta)}</span>'
    return '<span class="mv flat">&ndash;</span>'


def short(name: str) -> str:
    return (name.replace("Sharp Football Analysis", "Sharp")
            .replace("Bleacher Report", "B/R").replace(" Sports", ""))


def board_rows(week: dict, depth: int) -> tuple[str, str]:
    sources = [s["id"] for s in week["sources"]]
    names = {s["id"]: s["name"] for s in week["sources"]}
    head = ('<th class="l" style="width:34px">#</th><th style="width:52px">Move</th>'
            '<th class="l">Team</th><th>Rec</th><th>Score</th><th>High/Low</th>'
            '<th class="l">Spread</th>'
            + "".join(f'<th class="src">{E(short(names[s]))}</th>' for s in sources))

    biggest = max([t["spread"] for t in week["teams"].values()] + [1])
    rows = []
    for abbr, t in sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"]):
        cells = [
            f'<td class="l rk">{t["rank"]}</td>',
            f'<td>{movement_html(t.get("delta"))}</td>',
            f'<td class="l">{team_link(abbr, depth)}</td>',
            f'<td class="num">{E(t.get("record", ""))}</td>',
            f'<td class="score">{t["avg"]:.2f}</td>',
            f'<td class="num">{t["high"]}&ndash;{t["low"]}</td>',
            f'<td class="l"><span class="spread"><span class="meter">'
            f'<i style="width:{round(t["spread"] / biggest * 100)}%"></i></span>'
            f'<span class="num">{t["spread"]}</span></span></td>',
        ]
        cells += [f'<td class="num">{t["ranks"].get(s, "&ndash;")}</td>' for s in sources]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return head, "".join(rows)


def tiles_html(week: dict, depth: int) -> str:
    notes = week.get("notes") or {}
    ranked = sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"])
    top, bottom = ranked[0], ranked[-1]

    def tile(label: str, abbr: str, sub: str) -> str:
        t = info(abbr)
        up = "../" * depth
        return (f'<div class="card"><h3>{E(label)}</h3><div class="big">'
                f'{chip_html(abbr, 22)}<a href="{up}teams/{t["slug"]}/">{E(t["name"])}</a>'
                f'</div><div class="sub">{sub}</div></div>')

    out = [tile("No. 1 overall", top[0], f'Score {top[1]["avg"]} &middot; {E(top[1].get("record", ""))}')]
    riser, faller = notes.get("biggest_riser"), notes.get("biggest_faller")
    if riser and week["teams"][riser].get("delta"):
        for label, abbr in (("Biggest riser", riser), ("Biggest faller", faller)):
            if not abbr:
                continue
            d = week["teams"][abbr]["delta"]
            way = f"up {d}" if d > 0 else f"down {abs(d)}" if d else "unchanged"
            out.append(tile(label, abbr, f'{way} to #{week["teams"][abbr]["rank"]}'))
    else:
        out.append(tile("No. 32 overall", bottom[0], f'Score {bottom[1]["avg"]}'))
    divisive = notes.get("most_divisive")
    if len(week["sources"]) > 1 and divisive:
        d = week["teams"][divisive]
        out.append(tile("Most divisive", divisive,
                        f'Ranked #{d["high"]} to #{d["low"]} across outlets'))
    return "".join(out[:4])


def lanes_html(week: dict, depth: int) -> dict[str, str]:
    s = week.get("storylines") or {}
    names = {x["id"]: x["name"] for x in week["sources"]}
    up = "../" * depth

    def link(abbr: str) -> str:
        t = info(abbr)
        return f'<a href="{up}teams/{t["slug"]}/"><b>{E(t["name"])}</b></a>'

    def lane(items, render, empty):
        if not items:
            return f'<li class="none">{E(empty)}</li>'
        return "".join(f"<li>{render(i)}</li>" for i in items[:4])

    outliers = lane(
        s.get("outliers"),
        lambda o: (f'{link(o["team"])} at <b>#{o["rank"]}</b> on '
                   f'{E(names.get(o["source"], o["source"]))}<span class="why">'
                   f'{abs(o["gap"])} spots {"higher" if o["gap"] > 0 else "lower"} '
                   f'than the consensus #{o["consensus"]}</span>'),
        "Every outlet is within a few spots of the consensus this week.")
    divergent = lane(
        s.get("divergent"),
        lambda v: (f'{link(v["team"])} <span class="flag">{v["gap"]:+d}</span>'
                   f'<span class="why">#{v["rank"]} in the rankings, #{v["record_rank"]} '
                   f'on results ({E(v.get("record", ""))})</span>'),
        "No games played yet — this comparison starts once Week 1 is in the books."
        if not week.get("games_through") else
        "No team is far from where its record puts it.")
    market = lane(
        s.get("market"),
        lambda m: (f'{link(m["team"])} <span class="od">{E(m["odds"])}</span>'
                   f'<span class="why">#{m["rank"]} in the consensus, #{m["market_rank"]} '
                   f'at the book</span>'),
        "Betting odds are not available for this week.")
    return {"laneOutliers": outliers, "laneDiverge": divergent, "laneMarket": market}


def crumbs(season: int, weeks: list[dict], current: int, depth: int) -> str:
    """Real links between weeks.

    The week picker is a <select>, which a crawler cannot traverse — without
    this the archive is only reachable through the season hub, and pages sit
    further from the homepage than they need to.
    """
    up = "../" * depth
    numbers = sorted(w["week"] for w in weeks)
    i = numbers.index(current)
    prev_w = numbers[i - 1] if i > 0 else None
    next_w = numbers[i + 1] if i < len(numbers) - 1 else None

    parts = []
    if prev_w:
        parts.append(f'<a class="crumb prev" href="{up}{season}/week-{prev_w}/" rel="prev">'
                     f'&larr; Week {prev_w}</a>')
    parts.append(f'<a class="crumb" href="{up}{season}/">{season} archive</a>')
    if next_w:
        parts.append(f'<a class="crumb next" href="{up}{season}/week-{next_w}/" rel="next">'
                     f'Week {next_w} &rarr;</a>')
    return f'<nav class="crumbs" aria-label="Week navigation">{"".join(parts)}</nav>'


def week_strip(season: int, weeks: list[dict], current: int, depth: int) -> str:
    """Every week of the season as a plain link, so the whole archive is one
    hop from any board page."""
    up = "../" * depth
    links = "".join(
        f'<a href="{up}{season}/week-{w}/"'
        + (' aria-current="page"' if w == current else "")
        + f'>{w}</a>'
        for w in sorted(x["week"] for x in weeks))
    return (f'<nav class="weekstrip" aria-label="All weeks">'
            f'<span class="weekstrip-label">{season} weeks</span>{links}</nav>')


def sources_html(week: dict) -> str:
    out = []
    for s in week["sources"]:
        by = f'{E(s["author"])} &middot; ' if s.get("author") else ""
        out.append(f'<li><b>{E(s["name"])}</b><span>{by}{E((s.get("published") or "")[:10])}'
                   f'</span><br><a href="{E(s["url"])}" target="_blank" rel="noopener nofollow">'
                   f'{E((s.get("title") or "Read the article")[:72])}</a></li>')
    for f in week.get("failed_sources", []):
        out.append(f'<li class="warn"><b>{E(f["name"])}</b><span> not included this week</span>'
                   f'<br><span style="font-size:11.5px">{E(f["error"])}</span></li>')
    return "".join(out)


# --------------------------------------------------------------------------
# monetisation slots — each returns "" until its account exists, so an
# unconfigured site renders exactly the page it renders today
# --------------------------------------------------------------------------

def ad_slot(name: str, label: str = "Advertisement") -> str:
    slot = config.AD_SLOTS.get(name, "")
    if not config.ads_enabled() or not slot:
        return ""
    return (f'<aside class="adslot" aria-label="{E(label)}">'
            f'<span class="adlabel">{E(label)}</span>'
            f'<ins class="adsbygoogle" style="display:block" '
            f'data-ad-client="{E(config.AD_CLIENT)}" data-ad-slot="{E(slot)}" '
            f'data-ad-format="auto" data-full-width-responsive="true"></ins>'
            f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></aside>')


def ad_head() -> str:
    if not config.ads_enabled():
        return ""
    return ('<script async crossorigin="anonymous" '
            f'src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
            f'?client={E(config.AD_CLIENT)}"></script>')


def newsletter(compact: bool = False) -> str:
    if not config.newsletter_enabled():
        return ""
    cls = "signup compact" if compact else "signup"
    return (f'<section class="{cls}">'
            f'<div class="signup-copy"><h3>The Tuesday board, in your inbox</h3>'
            f'<p>{E(config.NEWSLETTER_NOTE)}</p></div>'
            f'<form class="signup-form" action="{E(config.NEWSLETTER_ACTION)}" '
            f'method="post" target="_blank">'
            f'<label class="sr-only" for="nl-email">Email address</label>'
            f'<input id="nl-email" type="email" name="email" required '
            f'placeholder="you@example.com" autocomplete="email">'
            f'<button type="submit">Subscribe</button></form>'
            f'<p class="signup-note">One email a week. Unsubscribe any time.</p>'
            f'</section>')


def affiliate_block() -> str:
    if not config.affiliates_enabled():
        return ""
    books = "".join(
        f'<a class="book" href="{E(u)}" rel="sponsored nofollow noopener" '
        f'target="_blank">{E(n)}</a>'
        for n, u in config.AFFILIATE_BOOKS.items())
    return (f'<aside class="books"><h3>Where these odds come from</h3>'
            f'<div class="booklist">{books}</div>'
            f'<p class="rg">{E(config.RESPONSIBLE_GAMBLING)} '
            f'Links to sportsbooks are paid partnerships.</p></aside>')


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------

def template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def write_page(rel: str, doc: str) -> Path:
    path = OUT / rel / "index.html" if rel else OUT / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return path


def board_page(season_data: dict, week: dict, rel: str, depth: int,
               *, is_home: bool) -> None:
    season = season_data["season"]
    n = len(week["sources"])
    ranked = sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"])
    leaders = ", ".join(info(a)["name"] for a, _ in ranked[:3])

    if is_home:
        title = f"NFL Power Rankings {season} — {week['label']} Consensus of {n} Outlets"
        desc = (f"Every major NFL power ranking averaged into one board. "
                f"{week['label']} {season}: {leaders} lead. Updated every Tuesday.")
    else:
        title = f"{season} {week['label']} NFL Power Rankings — Consensus of {n} Outlets"
        desc = (f"{season} {week['label']} NFL power rankings, averaged across {n} outlets. "
                f"{leaders} lead. Every outlet's rank for all 32 teams.")

    canonical = config.url(rel + "/" if rel else "")
    og = config.url(f"share/og/{season}-week-{week['week']:02d}.png")

    doc = template("index.html")
    doc = rewrite_links(doc, depth)
    head, rows = board_rows(week, depth)
    doc = fill(doc, "boardTitle", E(f"{season} {week['label']} Superpower Rankings"))
    doc = fill(doc, "srcCount", f"{n} outlet{'' if n == 1 else 's'}")
    doc = fill(doc, "head", head)
    doc = fill(doc, "rows", rows)
    doc = fill(doc, "cards", tiles_html(week, depth))
    for key, value in lanes_html(week, depth).items():
        doc = fill(doc, key, value)
    doc = fill(doc, "srcList", sources_html(week))

    nav = (crumbs(season, season_data["weeks"], week["week"], depth)
           + week_strip(season, season_data["weeks"], week["week"], depth))
    doc = doc.replace('<section class="cards" id="cards">',
                      nav + '<section class="cards" id="cards">', 1)

    # Monetisation slots sit between sections, never inside the board itself.
    doc = doc.replace('<section class="stories"', ad_slot("board_leader") + '<section class="stories"', 1)
    doc = doc.replace('<section class="sources" id="share">',
                      newsletter() + affiliate_block()
                      + ad_slot("in_content") + '<section class="sources" id="share">', 1)

    jsonld = [
        {"@context": "https://schema.org", "@type": "WebSite",
         "name": config.SITE_NAME, "url": config.SITE_URL,
         "description": config.TAGLINE},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": title, "numberOfItems": len(ranked),
         "itemListOrder": "https://schema.org/ItemListOrderAscending",
         "itemListElement": [
             {"@type": "ListItem", "position": t["rank"],
              "name": info(a)["name"],
              "url": config.url(f"teams/{info(a)['slug']}/")}
             for a, t in ranked]},
    ]
    doc = set_head(doc, title=title, description=desc, canonical=canonical,
                   og_image_url=og, jsonld=jsonld, extra=ad_head())
    doc = set_page_state(doc, {"view": "board", "season": season, "week": week["week"]})
    write_page(rel, doc)


def team_page(season_data: dict, week: dict, abbr: str, rel: str, depth: int) -> None:
    season = season_data["season"]
    t = info(abbr)
    e = week["teams"][abbr]
    n = len(week["sources"])

    title = f"{t['name']} Power Ranking — {season} {week['label']}"
    desc = (f"{t['name']} are ranked #{e['rank']} in the {season} {week['label']} "
            f"consensus, with a score of {e['avg']:.2f} across {n} outlets "
            f"(high #{e['high']}, low #{e['low']}). Week-by-week history and every "
            f"outlet's ranking.")
    canonical = config.url(rel + "/")
    og = config.url(f"share/og/{season}-{t['slug']}.png")

    doc = template("team.html")
    doc = rewrite_links(doc, depth)

    doc = fill(doc, "heroName", E(t["name"]))
    through = (f'{E(e.get("record", ""))} through Week {week["games_through"]}'
               if week.get("games_through") else "preseason")
    doc = fill(doc, "heroSub", f'{E(t["division"])} &middot; {through} '
                               f'&middot; {season} {E(week["label"])}')
    best = min(x["teams"][abbr]["rank"] for x in season_data["weeks"] if abbr in x["teams"])
    doc = fill(doc, "heroStats",
               f'<div><b>#{e["rank"]}</b><span>Superpower</span></div>'
               f'<div><b>{e["avg"]:.2f}</b><span>Score</span></div>'
               f'<div><b>{e["high"]}&ndash;{e["low"]}</b><span>Outlet high/low</span></div>'
               f'<div><b>{best}</b><span>Season best</span></div>')

    outlets = "".join(
        f'<tr><td class="l">{E(s["name"])}</td>'
        f'<td class="score">{e["ranks"].get(s["id"], "&ndash;")}</td>'
        f'<td>{movement_html((e.get("source_delta") or {}).get(s["id"]))}</td>'
        f'<td class="l"><a href="{E(s["url"])}" target="_blank" rel="noopener nofollow">'
        f'Article &#8599;</a></td></tr>'
        for s in week["sources"])
    doc = fill(doc, "outlets", outlets)
    doc = fill(doc, "outletTitle", f'Outlet by outlet &mdash; {E(week["label"])}')

    games = []
    for g in season_data["games"].get(abbr, []):
        opp = info(g["opponent"])
        score = (f'{g["points_for"]}&ndash;{g["points_against"]}'
                 if g.get("points_for") is not None else E(g.get("detail") or "TBD"))
        result = (f'<span class="res {g["result"]}">{g["result"]}</span>'
                  if g.get("result") else "&ndash;")
        margin = ("" if g.get("points_for") is None else
                  f'{g["points_for"] - g["points_against"]:+d}')
        games.append(f'<tr><td class="l">{E(g["label"])}</td>'
                     f'<td class="l"><a class="team" href="{"../" * depth}teams/{opp["slug"]}/">'
                     f'{chip_html(g["opponent"], 20)}<span>'
                     f'{"" if g["home"] else "@ "}{E(opp["nickname"])}</span></a></td>'
                     f'<td>{result}</td><td class="num">{score}</td>'
                     f'<td class="num">{margin}</td><td class="l">&ndash;</td></tr>')
    doc = fill(doc, "games", "".join(games))

    ids = [s["id"] for s in season_data["sources"]]
    doc = fill(doc, "wbwHead",
               '<th class="l">Week</th><th>Superpower</th><th>Move</th><th>Score</th>'
               + "".join(f'<th class="src">{E(short(season_data["sourcesBy"][i]))}</th>'
                         for i in ids))
    wbw = []
    for w in sorted(season_data["weeks"], key=lambda x: -x["week"]):
        row = w["teams"].get(abbr)
        if not row:
            continue
        wbw.append(f'<tr><td class="l">{E(w["label"])}</td><td class="rk">{row["rank"]}</td>'
                   f'<td>{movement_html(row.get("delta"))}</td>'
                   f'<td class="score">{row["avg"]:.2f}</td>'
                   + "".join(f'<td class="num">{row["ranks"].get(i, "&ndash;")}</td>'
                             for i in ids) + "</tr>")
    doc = fill(doc, "wbw", "".join(wbw))

    up = "../" * depth
    back = (f'<nav class="crumbs" aria-label="Breadcrumb">'
            f'<a class="crumb" href="{up}">Rankings</a>'
            f'<a class="crumb" href="{up}{season}/">{season} archive</a>'
            f'<a class="crumb" href="{up}{season}/week-{week["week"]}/">{E(week["label"])}</a>'
            f'</nav>')
    doc = doc.replace('<section class="cards" id="context">',
                      back + '<section class="cards" id="context">', 1)
    doc = doc.replace('<div class="grid2">',
                      ad_slot("team_side") + newsletter(compact=True) + '<div class="grid2">', 1)

    jsonld = [{
        "@context": "https://schema.org", "@type": "SportsTeam",
        "name": t["name"], "sport": "American Football",
        "memberOf": {"@type": "SportsOrganization", "name": "National Football League"},
        "url": canonical,
    }, {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Rankings", "item": config.SITE_URL},
            {"@type": "ListItem", "position": 2, "name": f"{season} season",
             "item": config.url(f"{season}/")},
            {"@type": "ListItem", "position": 3, "name": t["name"], "item": canonical},
        ]}]
    doc = set_head(doc, title=title, description=desc, canonical=canonical,
                   og_image_url=og, og_type="profile", jsonld=jsonld, extra=ad_head())
    doc = set_page_state(doc, {"view": "team", "season": season,
                               "week": week["week"], "team": abbr})
    write_page(rel, doc)


def hub_page(season_data: dict) -> None:
    """A season index. Mostly here so every week and team is one hop from a
    crawlable link rather than behind a dropdown."""
    season = season_data["season"]
    weeks = sorted(season_data["weeks"], key=lambda w: -w["week"])
    latest = weeks[0]

    week_links = "".join(
        f'<li><a href="week-{w["week"]}/"><b>{E(w["label"])}</b>'
        f'<span class="why">{len(w["sources"])} outlets &middot; '
        f'#1 {E(info(min(w["teams"], key=lambda a: w["teams"][a]["rank"]))["name"])}'
        f'</span></a></li>' for w in weeks)
    team_links = "".join(
        f'<li><a class="team" href="../teams/{t["slug"]}/">{chip_html(t["abbr"], 22)}'
        f'<span class="nm">{E(t["name"])}</span></a></li>'
        for t in sorted(season_data["teams"], key=lambda x: x["name"]))

    body = (f'<h1>{season} NFL Power Rankings Archive</h1>'
            f'<p class="lede">Every week of the {season} season, averaged across '
            f'{len(latest["sources"])} outlets. Pick a week or a team.</p>'
            f'{newsletter()}'
            f'<section class="tablecard"><div class="tablehead"><h2>Weeks</h2></div>'
            f'<ul class="linklist">{week_links}</ul></section>'
            f'{ad_slot("in_content")}'
            f'<section class="tablecard" style="margin-top:16px">'
            f'<div class="tablehead"><h2>All 32 teams</h2></div>'
            f'<ul class="linklist grid">{team_links}</ul></section>')

    title = f"{season} NFL Power Rankings — Every Week, Every Outlet"
    desc = (f"The complete {season} NFL power rankings archive: all "
            f"{len(weeks)} weeks, averaged across every major outlet, plus a page "
            f"for each of the 32 teams.")
    doc = shell_page(title=title, description=desc, rel=str(season), depth=1,
                     body=body, og=config.url(f"share/og/{season}-week-"
                                              f"{latest['week']:02d}.png"),
                     state={"view": "board", "season": season, "week": latest["week"]})
    write_page(str(season), doc)


def shell_page(*, title: str, description: str, rel: str, depth: int, body: str,
               og: str | None = None, state: dict | None = None,
               jsonld: list[dict] | None = None, noindex: bool = False) -> str:
    """A plain content page using the site chrome, for things the app does not own."""
    doc = template("index.html")
    doc = rewrite_links(doc, depth)
    doc = re.sub(r"<main class=\"wrap\">.*?</main>", f'<main class="wrap">{body}</main>',
                 doc, count=1, flags=re.S)
    # The week/season controls belong to the board; a content page has none.
    doc = re.sub(r'<div class="weekbar">.*?</div>\s*</div>\s*</div>', "", doc,
                 count=1, flags=re.S)
    doc = set_head(doc, title=title, description=description,
                   canonical=config.url(rel + "/" if rel else ""),
                   og_image_url=og or config.url("share/og/default.png"),
                   jsonld=jsonld, extra=ad_head())
    if noindex:
        doc = doc.replace('content="index,follow,max-image-preview:large"',
                          'content="noindex,follow"')
    doc = set_page_state(doc, state or {"view": "static"})
    # A static page has no app to boot.
    doc = doc.replace('<script type="module" src="' + "../" * depth + 'assets/index.js">'
                      '</script>', "")
    return doc


LEGAL_STYLE = """
<style>
.prose { max-width: 68ch; }
.prose h1 { font-family: var(--display); font-size: 34px; text-transform: uppercase;
  margin: 0 0 6px; }
.prose h2 { font-family: var(--display); font-size: 21px; text-transform: uppercase;
  margin: 26px 0 8px; }
.prose p, .prose li { color: var(--ink-2); line-height: 1.65; }
.prose ul { padding-left: 18px; }
.prose .updated { color: var(--muted); font-size: 13px; margin: 0 0 18px; }
.lede { color: var(--muted); max-width: 68ch; margin: 0 0 22px; }
.linklist { list-style: none; margin: 0; padding: 0; }
.linklist li { border-bottom: 1px solid var(--line-soft); }
.linklist li:last-child { border-bottom: 0; }
.linklist a { display: flex; align-items: center; gap: 9px; padding: 11px 17px; }
.linklist a:hover { background: var(--line-soft); }
.linklist.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.linklist.grid li { border-bottom: 1px solid var(--line-soft); }
</style>
"""


def legal_pages() -> None:
    today = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    contact = (f'<a href="mailto:{E(config.CONTACT_EMAIL)}">{E(config.CONTACT_EMAIL)}</a>'
               if config.CONTACT_EMAIL else "the contact address listed on this site")

    ads_para = ("<p>This site does not currently serve advertising.</p>"
                if not config.ads_enabled() else
                "<p>We show advertising through Google AdSense. Google and its partners "
                "may use cookies or device identifiers to serve and measure ads. You can "
                "review and change your choices at "
                "<a href=\"https://adssettings.google.com\" rel=\"noopener\">Google Ad "
                "Settings</a>, and read Google's practices at "
                "<a href=\"https://policies.google.com/technologies/partner-sites\" "
                "rel=\"noopener\">How Google uses information from sites that use its "
                "services</a>.</p>")

    affiliate_para = ("" if not config.affiliates_enabled() else
                      "<h2>Affiliate links</h2><p>Some links to sportsbooks are paid "
                      "partnerships: if you open an account through one, we may earn a "
                      "commission. This never changes how a team is ranked — rankings come "
                      "from published articles and are averaged mechanically. "
                      f"{E(config.RESPONSIBLE_GAMBLING)}</p>")

    privacy = f"""<div class="prose">
<h1>Privacy</h1><p class="updated">Last updated {today}</p>
<p>Superpower Rankings is a static website. We do not ask you to create an account,
and we do not collect names, addresses or payment details.</p>
<h2>What is stored on your device</h2>
<p>The site remembers one thing locally, in your browser: whether you chose light or
dark mode. It never leaves your device and we cannot read it.</p>
<h2>Analytics</h2>
<p>We use Cloudflare Web Analytics, which is cookie-free and does not fingerprint or
track individuals across sites. It reports aggregate counts such as page views and
referring sites.</p>
<h2>Advertising</h2>{ads_para}
<h2>Email</h2>
<p>If you subscribe to the weekly email, your address is stored by our email provider
solely to send that email. Every message includes an unsubscribe link, and unsubscribing
deletes you from the list.</p>
<h2>Links out</h2>
<p>Every ranking links to the outlet that published it. Those sites have their own
privacy practices, which we do not control.</p>
<h2>Your choices</h2>
<p>You can clear this site's local storage at any time in your browser settings, and
unsubscribe from email with one click. For anything else, contact {contact}.</p>
</div>"""

    terms = f"""<div class="prose">
<h1>Terms</h1><p class="updated">Last updated {today}</p>
<h2>What this site is</h2>
<p>Superpower Rankings collects power rankings published by other outlets and averages
them. The rankings belong to the outlets that made them, and every one is credited and
linked back to its source article. We publish the numbers and our own analysis of them,
not other people's writing.</p>
<h2>Not affiliated with the NFL</h2>
<p>This is an independent project. It is not affiliated with, endorsed by, or sponsored
by the National Football League or any of its clubs. Team names and marks belong to
their respective owners and are used to identify the teams being written about.</p>
<h2>Accuracy</h2>
<p>Data is gathered automatically and published as-is. Outlets change their formats and
occasionally publish late; when a ranking cannot be read completely and correctly, that
outlet is left out of the week's average and shown as a miss rather than guessed at.
Nothing here is betting advice.</p>
{affiliate_para}
<h2>Using the data</h2>
<p>The aggregated data is available as JSON and you are welcome to build on it. Please
credit Superpower Rankings and link back. Do not scrape aggressively — the files are
static and cheap to fetch once.</p>
<h2>Contact</h2><p>Questions go to {contact}.</p>
</div>"""

    for rel, title, desc, body in (
        ("privacy", "Privacy — Superpower Rankings",
         "What Superpower Rankings stores, what it does not, and how to opt out.", privacy),
        ("terms", "Terms — Superpower Rankings",
         "How Superpower Rankings sources rankings, credits outlets, and what you may "
         "do with the data.", terms),
    ):
        doc = shell_page(title=title, description=desc, rel=rel, depth=1,
                         body=body + LEGAL_STYLE)
        write_page(rel, doc)


def api_page(seasons: list[dict]) -> None:
    rows = "".join(
        f'<tr><td class="l"><code>/data/season-{s["season"]}.json</code></td>'
        f'<td class="l">Every week of {s["season"]}: consensus ranks, each outlet\'s '
        f'rank, records, schedule and outlet accuracy.</td></tr>' for s in seasons)
    body = f"""<div class="prose">
<h1>Data API</h1>
<p class="lede">The whole archive is static JSON. No key, no rate limit, no signup —
just fetch the file. Please credit Superpower Rankings and link back.</p>
</div>
<section class="tablecard"><div class="tablehead"><h2>Endpoints</h2></div>
<div class="scroller"><table><thead><tr><th class="l">URL</th><th class="l">What it is</th>
</tr></thead><tbody>
<tr><td class="l"><code>/data/index.json</code></td><td class="l">Which seasons and weeks
exist. Start here.</td></tr>
{rows}
</tbody></table></div></section>
<div class="prose"><h2>Shape</h2>
<p>A season file holds <code>teams</code>, <code>sources</code>, <code>weeks</code>,
<code>games</code>, <code>records</code>, <code>market</code> and <code>accuracy</code>.
Each week holds a <code>teams</code> map keyed by team abbreviation, and each team entry
carries its consensus <code>rank</code>, the <code>avg</code> score, per-outlet
<code>ranks</code>, movement, spread, strength of schedule and market comparison.</p>
<h2>Fair use</h2>
<p>These are static files on a CDN, so a normal fetch costs nothing. If you need the whole
archive, pull each season file once and cache it — the data only changes on Tuesdays.</p>
</div>{LEGAL_STYLE}"""
    doc = shell_page(title="NFL Power Rankings Data API — Superpower Rankings",
                     description="Free static JSON for the whole NFL consensus power "
                                 "rankings archive: per-outlet ranks, movement, schedule "
                                 "and outlet accuracy. No key required.",
                     rel="api", depth=1, body=body)
    write_page("api", doc)


# --------------------------------------------------------------------------
# discovery files
# --------------------------------------------------------------------------

def write_sitemap(urls: list[tuple[str, str, str]]) -> None:
    """urls = [(loc, lastmod, changefreq)]"""
    items = "".join(
        f"<url><loc>{E(loc)}</loc><lastmod>{lastmod}</lastmod>"
        f"<changefreq>{freq}</changefreq></url>"
        for loc, lastmod, freq in urls)
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + items + "</urlset>\n", encoding="utf-8")

    (OUT / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# The archive is static JSON and free to use — see /api/ — but please\n"
        "# fetch each file once and cache it rather than crawling it repeatedly.\n"
        "Crawl-delay: 1\n"
        "\n"
        f"Sitemap: {config.url('sitemap.xml')}\n", encoding="utf-8")


def write_extras(urls: list[tuple[str, str, str]]) -> None:
    """Files that are not pages: the IndexNow key, ads.txt, and a 404."""
    from superpower import indexnow

    if config.INDEXNOW_KEY:
        (OUT / f"{config.INDEXNOW_KEY}.txt").write_text(
            indexnow.key_file_body(), encoding="utf-8")

    ads = config.ads_txt()
    if ads:
        (OUT / "ads.txt").write_text(ads, encoding="utf-8")

    # GitHub Pages serves 404.html for anything it cannot find.
    body = ('<div class="prose"><h1>Page not found</h1>'
            '<p class="lede">That URL does not exist here. The rankings update every '
            'Tuesday and old weeks keep their own address, so a stale link usually '
            'means a week that was never published.</p>'
            '<p><a class="crumb" href="/">Current rankings</a> '
            '<a class="crumb" href="/2026/">2026 archive</a> '
            '<a class="crumb" href="/accuracy/">Outlet accuracy</a></p></div>'
            + LEGAL_STYLE)
    doc = shell_page(title="Page not found — Superpower Rankings",
                     description="That page does not exist.",
                     rel="404", depth=0, body=body, noindex=True)
    (OUT / "404.html").write_text(doc, encoding="utf-8")


def write_feed(season_data: dict) -> None:
    """A full-content feed.

    Buttondown, beehiiv, Mailchimp and Kit can all run an RSS-to-email
    campaign: point one at this feed and the weekly newsletter sends itself
    every Tuesday with no further code. That only works if the feed carries
    the actual content, so each item ships the top ten and the week's
    storylines in <content:encoded>, not just a one-line summary.
    """
    season = season_data["season"]
    weeks = sorted(season_data["weeks"], key=lambda w: -w["week"])[:20]
    names = {x["id"]: x["name"] for x in season_data["sources"]}
    items = []

    for w in weeks:
        ranked = sorted(w["teams"].items(), key=lambda kv: kv[1]["rank"])
        link = config.url(f"{season}/week-{w['week']}/")
        title = f"{season} {w['label']} NFL Power Rankings"
        top = ", ".join(f"{i}. {info(a)['name']}" for i, (a, _) in enumerate(ranked[:5], 1))
        summary = f"Consensus of {len(w['sources'])} outlets. {top}."

        rows = "".join(
            f"<tr><td><b>{t['rank']}</b></td><td>{E(info(a)['name'])}</td>"
            f"<td>{t['avg']:.2f}</td><td>{'' if not t.get('delta') else ('&#9650;' if t['delta'] > 0 else '&#9660;') + str(abs(t['delta']))}</td></tr>"
            for a, t in ranked[:10])
        story = (w.get("storylines") or {})
        bullets = []
        for o in story.get("outliers", [])[:2]:
            side = "higher" if o["gap"] > 0 else "lower"
            bullets.append(f"<li><b>{E(info(o['team'])['name'])}</b> — "
                           f"{E(names.get(o['source'], o['source']))} has them at #{o['rank']}, "
                           f"{abs(o['gap'])} spots {side} than the consensus.</li>")
        for m in story.get("market", [])[:2]:
            who = "the market" if m["gap"] > 0 else "the media"
            bullets.append(f"<li><b>{E(info(m['team'])['name'])}</b> — #{m['rank']} in the "
                           f"consensus, #{m['market_rank']} at the book ({E(m['odds'])}); "
                           f"{who} is the believer.</li>")

        content = (f"<p>Every major NFL power ranking, averaged. "
                   f"{len(w['sources'])} outlets this week.</p>"
                   f"<table><thead><tr><th>#</th><th>Team</th><th>Score</th><th></th></tr>"
                   f"</thead><tbody>{rows}</tbody></table>"
                   + (f"<h3>What to argue about</h3><ul>{''.join(bullets)}</ul>" if bullets else "")
                   + f'<p><a href="{E(link)}">See all 32 teams and every outlet&#8217;s rank</a></p>')

        try:
            when = datetime.fromisoformat(w["generated"].replace("Z", "+00:00"))
        except Exception:
            when = datetime.now(timezone.utc)

        items.append(
            f"<item><title>{E(title)}</title>"
            f"<link>{E(link)}</link>"
            f'<guid isPermaLink="true">{E(link)}</guid>'
            f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
            f"<description>{E(summary)}</description>"
            f"<content:encoded><![CDATA[{content}]]></content:encoded></item>")

    (OUT / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{E(config.SITE_NAME)}</title>"
        f"<link>{E(config.SITE_URL)}</link>"
        f'<atom:link href="{E(config.url("feed.xml"))}" rel="self" type="application/rss+xml"/>'
        f"<description>{E(config.TAGLINE)}</description>"
        "<language>en-us</language>"
        + "".join(items) + "</channel></rss>\n", encoding="utf-8")


# --------------------------------------------------------------------------
# walk
# --------------------------------------------------------------------------

def main() -> None:
    data_dir = ROOT / "data"
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    default_season = index["default_season"]

    seasons: dict[int, dict] = {}
    for entry in index["seasons"]:
        payload = json.loads(
            (data_dir / f"season-{entry['season']}.json").read_text(encoding="utf-8"))
        payload["sourcesBy"] = {s["id"]: s["name"] for s in payload["sources"]}
        seasons[entry["season"]] = payload

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls: list[tuple[str, str, str]] = []
    og_dir = OUT / "share" / "og"
    pages = 0

    for season, payload in seasons.items():
        if not payload["weeks"]:
            continue
        latest = max(payload["weeks"], key=lambda w: w["week"])
        is_default = season == default_season

        for week in payload["weeks"]:
            rel = f"{season}/week-{week['week']}"
            board_page(payload, week, rel, depth=2, is_home=False)
            og_image.write(og_image.week_card(week, season, len(week["sources"])),
                           og_dir / f"{season}-week-{week['week']:02d}.png")
            urls.append((config.url(rel + "/"), today,
                         "daily" if week is latest else "yearly"))
            pages += 1

        hub_page(payload)
        urls.append((config.url(f"{season}/"), today, "weekly"))
        pages += 1

        # Team pages live at /teams/<slug>/ for the current season and
        # /<season>/teams/<slug>/ for the archive.
        for team in payload["teams"]:
            abbr = team["abbr"]
            if abbr not in latest["teams"]:
                continue
            rel = (f"teams/{team['slug']}" if is_default
                   else f"{season}/teams/{team['slug']}")
            depth = 2 if is_default else 3
            team_page(payload, latest, abbr, rel, depth)
            og_image.write(og_image.team_card(abbr, latest, season),
                           og_dir / f"{season}-{team['slug']}.png")
            urls.append((config.url(rel + "/"), today, "weekly"))
            pages += 1

        if is_default:
            board_page(payload, latest, "", depth=0, is_home=True)
            urls.insert(0, (config.SITE_URL, today, "daily"))
            og_image.write(og_image.week_card(latest, season, len(latest["sources"])),
                           og_dir / "default.png")
            write_feed(payload)
            pages += 1

    # Interactive tools keep their own pages; they carry no unique text worth
    # ranking, so they are linked but left out of the sitemap's priority set.
    for name, rel, title, desc in (
        ("compare.html", "compare", "Compare Any Two NFL Teams — Superpower Rankings",
         "Put any two NFL teams side by side: consensus rank, every outlet's rank, "
         "record, strength of schedule, market odds and both rank histories."),
        ("accuracy.html", "accuracy", "Which NFL Power Rankings Are Actually Right?",
         "Every outlet scored against how teams actually finished, by average error "
         "and rank correlation — and whether the consensus beats its own ingredients."),
    ):
        doc = template(name)
        doc = rewrite_links(doc, 1)
        doc = set_head(doc, title=title, description=desc,
                       canonical=config.url(rel + "/"),
                       og_image_url=config.url("share/og/default.png"), extra=ad_head())
        doc = set_page_state(doc, {"view": rel, "season": default_season})
        write_page(rel, doc)
        urls.append((config.url(rel + "/"), today, "weekly"))
        pages += 1

    legal_pages()
    api_page(index["seasons"])
    for rel in ("privacy", "terms", "api"):
        urls.append((config.url(rel + "/"), today, "monthly"))
        pages += 1

    write_sitemap(urls)
    write_extras(urls)

    print(f"prerendered {pages} pages, {len(urls)} sitemap entries")
    print(f"  og cards: {sum(1 for _ in og_dir.glob('*.png'))}")


if __name__ == "__main__":
    main()
