"""The weekly email digest.

Builds a self-contained HTML email — inline styles, table layout, no external
assets — because that is the only thing mail clients render reliably.

Nothing is sent unless you ask for it. `build` writes the file; `send` needs
explicit SMTP settings in the environment and an explicit `--send` flag.
"""
from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from .teams import info

TOP_N = 10

INK = "#0e1620"
NAVY = "#10243f"
RULE = "#c8102e"
MUTED = "#6a7887"
LINE = "#e6eaef"
UP = "#0f7b4f"
DOWN = "#c0392b"


def _esc(s) -> str:
    return html.escape(str(s))


def _move(delta) -> str:
    if delta is None:
        return f'<span style="color:{MUTED};font-size:11px">NEW</span>'
    if delta > 0:
        return f'<span style="color:{UP};font-weight:700">&#9650; {delta}</span>'
    if delta < 0:
        return f'<span style="color:{DOWN};font-weight:700">&#9660; {abs(delta)}</span>'
    return f'<span style="color:{MUTED}">&ndash;</span>'


def _story_lines(week: dict, names: dict[str, str]) -> list[str]:
    s = week.get("storylines") or {}
    out = []
    for o in s.get("outliers", [])[:2]:
        side = "higher" if o["gap"] > 0 else "lower"
        out.append(f'<b>{_esc(info(o["team"])["name"])}</b> — {_esc(names.get(o["source"], o["source"]))} '
                   f'has them at #{o["rank"]}, {abs(o["gap"])} spots {side} than the consensus #{o["consensus"]}.')
    for d in s.get("divergent", [])[:2]:
        side = "ahead of" if d["gap"] > 0 else "behind"
        out.append(f'<b>{_esc(info(d["team"])["name"])}</b> ({_esc(d.get("record", ""))}) sit at #{d["rank"]} '
                   f'but rank #{d["record_rank"]} on results — the media is {abs(d["gap"])} spots '
                   f'{side} what they have earned.')
    for m in s.get("market", [])[:2]:
        who = "the market" if m["gap"] > 0 else "the media"
        out.append(f'<b>{_esc(info(m["team"])["name"])}</b> — #{m["rank"]} in the consensus but '
                   f'#{m["market_rank"]} at the book ({_esc(m["odds"])}); {who} is the believer.')
    return out


def build(site: dict, week: dict, base_url: str = "") -> str:
    names = {s["id"]: s["name"] for s in site["sources"]}
    rows = sorted(week["teams"].items(), key=lambda kv: kv[1]["rank"])[:TOP_N]
    link = base_url.rstrip("/")

    body = [
        f'<tr><td style="background:{NAVY};padding:22px 26px 18px;border-bottom:4px solid {RULE}">'
        f'<div style="font:700 27px/1 Helvetica,Arial,sans-serif;color:#fff;letter-spacing:.5px">'
        f'&#9889; SUPERPOWER RANKINGS</div>'
        f'<div style="font:13px Helvetica,Arial,sans-serif;color:#fff;opacity:.72;'
        f'letter-spacing:2px;padding-top:7px">{_esc(site["season"])} '
        f'&middot; {_esc(week["label"]).upper()} &middot; '
        f'{len(week["sources"])} OUTLET{"" if len(week["sources"]) == 1 else "S"}</div></td></tr>'
    ]

    table = [f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">']
    for abbr, e in rows:
        t = info(abbr)
        table.append(
            f'<tr>'
            f'<td style="padding:9px 8px;border-bottom:1px solid {LINE};font:700 17px Helvetica,Arial;'
            f'color:{INK};width:34px">{e["rank"]}</td>'
            f'<td style="padding:9px 8px;border-bottom:1px solid {LINE};width:52px">{_move(e.get("delta"))}</td>'
            f'<td style="padding:9px 8px;border-bottom:1px solid {LINE};font:15px Helvetica,Arial;color:{INK}">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:3px;'
            f'background:{t["primary"]};margin-right:8px"></span><b>{_esc(t["name"])}</b>'
            f'<span style="color:{MUTED}"> &nbsp;{_esc(e.get("record", ""))}</span></td>'
            f'<td style="padding:9px 8px;border-bottom:1px solid {LINE};font:700 15px Helvetica,Arial;'
            f'color:{INK};text-align:right">{e["avg"]:.2f}</td>'
            f'</tr>')
    table.append("</table>")

    body.append(f'<tr><td style="padding:20px 26px 4px">'
                f'<div style="font:700 15px Helvetica,Arial;color:{INK};padding-bottom:8px">'
                f'Top {TOP_N}</div>{"".join(table)}</td></tr>')

    stories = _story_lines(week, names)
    if stories:
        items = "".join(
            f'<li style="padding-bottom:9px;font:14px/1.5 Helvetica,Arial;color:{INK}">{s}</li>'
            for s in stories)
        body.append(f'<tr><td style="padding:20px 26px 0">'
                    f'<div style="font:700 15px Helvetica,Arial;color:{INK};padding-bottom:6px">'
                    f'What to argue about this week</div>'
                    f'<ul style="margin:0;padding-left:18px">{items}</ul></td></tr>')

    sources = " &middot; ".join(
        f'<a href="{_esc(s["url"])}" style="color:{MUTED}">{_esc(s["name"])}</a>'
        for s in week["sources"])
    cta = (f'<p style="margin:0 0 12px"><a href="{_esc(link)}" '
           f'style="font:700 14px Helvetica,Arial;color:{NAVY}">See all 32 teams &rarr;</a></p>'
           if link else "")
    body.append(f'<tr><td style="padding:22px 26px 26px;border-top:1px solid {LINE}">{cta}'
                f'<p style="margin:0;font:12px/1.6 Helvetica,Arial;color:{MUTED}">'
                f'Rankings from {sources}. Every ranking belongs to its outlet.</p></td></tr>')

    return (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Superpower Rankings — {_esc(site["season"])} {_esc(week["label"])}</title></head>'
        f'<body style="margin:0;background:#f2f5f8">'
        f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
        f'<tr><td align="center" style="padding:22px 12px">'
        f'<table width="600" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;background:#fff;border:1px solid {LINE};border-radius:8px;'
        f'overflow:hidden;max-width:600px">{"".join(body)}</table>'
        f'</td></tr></table></body></html>'
    )


def write(site: dict, week: dict, out_dir: Path, base_url: str = "") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = build(site, week, base_url)
    paths = [out_dir / f"digest-{site['season']}-{week['week']:02d}.html",
             out_dir / "latest-digest.html"]
    for p in paths:
        p.write_text(doc, encoding="utf-8")
    return paths


def send(doc: str, subject: str, recipients: list[str]) -> None:
    """Send the digest. Requires SMTP_HOST, SMTP_USER, SMTP_PASS and MAIL_FROM.

    Deliberately opt-in: nothing in the normal update path calls this.
    """
    host, user = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_USER")
    password, sender = os.environ.get("SMTP_PASS"), os.environ.get("MAIL_FROM")
    missing = [n for n, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                              ("SMTP_PASS", password), ("MAIL_FROM", sender)) if not v]
    if missing:
        raise SystemExit("cannot send — missing environment variables: " + ", ".join(missing))
    if not recipients:
        raise SystemExit("cannot send — no recipients given")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content("This digest is best viewed as HTML.")
    msg.add_alternative(doc, subtype="html")

    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
