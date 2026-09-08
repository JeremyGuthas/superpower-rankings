"""Ready-to-post copy for the weekly push.

Search traffic takes months to build; posting does not. This writes the text
for each channel from the week's actual data, so the Tuesday job produces
something that can be pasted straight into Reddit or X without rewriting.

The angles it leads with are the ones no single outlet can publish: which
outlet is out on a limb, where the rankings and the results disagree, and
where the media and the betting market part ways.
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .teams import info


def _sentences(week: dict, names: dict[str, str]) -> list[str]:
    s = week.get("storylines") or {}
    out = []
    for o in s.get("outliers", [])[:2]:
        side = "higher" if o["gap"] > 0 else "lower"
        out.append(f"**{info(o['team'])['name']}** — {names.get(o['source'], o['source'])} "
                   f"has them at #{o['rank']}, {abs(o['gap'])} spots {side} than the "
                   f"consensus #{o['consensus']}.")
    for d in s.get("divergent", [])[:2]:
        side = "ahead of" if d["gap"] > 0 else "behind"
        out.append(f"**{info(d['team'])['name']}** ({d.get('record','')}) sit #{d['rank']} "
                   f"but rank #{d['record_rank']} on results — {abs(d['gap'])} spots "
                   f"{side} what they have earned.")
    for m in s.get("market", [])[:2]:
        who = "the market" if m["gap"] > 0 else "the media"
        out.append(f"**{info(m['team'])['name']}** — #{m['rank']} in the consensus but "
                   f"#{m['market_rank']} at the book ({m['odds']}); {who} is the believer.")
    return out


def build(site: dict, week: dict) -> str:
    season = site["season"]
    names = {s["id"]: s["name"] for s in site["sources"]}
    outlets = [s["name"] for s in week["sources"]]
    ranked = sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"])
    top10 = "\n".join(
        f"{t['rank']}. {info(a)['name']} — {t['avg']:.2f}"
        + ("" if t.get("delta") in (None, 0)
           else f" ({'▲' if t['delta'] > 0 else '▼'}{abs(t['delta'])})")
        for a, t in ranked[:10])

    week_url = config.url(f"{season}/week-{week['week']}/")
    image_url = config.url(f"share/og/{season}-week-{week['week']:02d}.png")
    lines = _sentences(week, names)
    bullets = "\n".join(f"- {line}" for line in lines) or "- Unusually broad agreement this week."

    reddit_title = (f"[OC] {season} {week['label']} NFL Power Rankings — "
                    f"every major outlet averaged into one board")
    x_lead = lines[0].replace("**", "") if lines else \
        f"{info(ranked[0][0])['name']} lead the consensus."

    return f"""# Weekly share kit — {season} {week['label']}

Generated automatically. Paste as-is; nothing here needs rewriting.

Image to attach: {image_url}
Page to link:    {week_url}

---

## Reddit (r/nfl, and the subs for teams named below)

**Title**

{reddit_title}

**Body**

I average every major NFL power ranking into one consensus board —
{", ".join(outlets)} this week. Full table with each outlet's rank for all 32:
{week_url}

Top 10:

{top10}

What stood out:

{bullets}

The whole archive is free JSON if anyone wants to play with it: {config.url("api/")}

---

## X / Bluesky

{season} {week['label']} NFL power rankings — {len(outlets)} outlets averaged into one board.

{x_lead}

Full 32: {week_url}

---

## One-line version, for a group chat

{season} {week['label']} consensus rankings, {len(outlets)} outlets averaged: {week_url}

---

## Where to post

- r/nfl — use the Reddit block above
- The team subs for anyone named in "what stood out"; those readers care most
- Any fantasy or betting Discord you are in

Posting Tuesday morning, while the outlets' own articles are fresh, is what
gets traction. Reply to your own post with the source links rather than
stacking them in the body — it reads less like promotion.
"""


def write(site: dict, week: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = build(site, week)
    paths = [out_dir / f"kit-{site['season']}-{week['week']:02d}.md",
             out_dir / "latest-kit.md"]
    for p in paths:
        p.write_text(text, encoding="utf-8")
    return paths
