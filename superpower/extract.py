"""Turn an outlet's article into a validated 1-32 ranking.

Outlets format rankings a dozen different ways, but nearly all of them emit
either numbered headings or numbered lines. We try each strategy in turn and
accept the first result that is a clean permutation of 1-32 over 32 distinct
teams. Anything less is rejected outright — publishing a half-parsed ranking
is worse than publishing none.
"""
from __future__ import annotations

import html
import logging
import re

from .teams import TEAMS, find_in_text, resolve

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)


def to_text(markup: str) -> str:
    """Strip markup to newline-separated visible text."""
    s = _SCRIPT.sub(" ", markup)
    s = re.sub(r"<(br|/p|/h[1-6]|/li|/div|/td|/tr)\b[^>]*>", "\n", s, flags=re.I)
    s = _TAG.sub("\n", s)
    s = html.unescape(s)
    lines = (re.sub(r"[ \t ]+", " ", ln).strip() for ln in s.split("\n"))
    return "\n".join(ln for ln in lines if ln)


class RankParseError(RuntimeError):
    pass


def validate(pairs: list[tuple[int, str]]) -> dict[str, int]:
    """Accept only a complete, duplicate-free 1-32 ranking."""
    ranks: dict[str, int] = {}
    seen: set[int] = set()
    for rank, abbr in pairs:
        if rank in seen or abbr in ranks:
            continue  # first mention wins; later repeats are cross-references
        seen.add(rank)
        ranks[abbr] = rank
    if len(ranks) != 32:
        raise RankParseError(f"found {len(ranks)} teams, expected 32")
    missing = set(TEAMS) - set(ranks)
    if missing:
        raise RankParseError(f"missing teams: {sorted(missing)}")
    if sorted(ranks.values()) != list(range(1, 33)):
        raise RankParseError("ranks are not a clean 1-32 permutation")
    return ranks


# --- strategies ------------------------------------------------------------

_HEADING = re.compile(r"<h([2-4])\b[^>]*>(.*?)</h\1>", re.S | re.I)
# "1. Los Angeles Rams" / "1 Los Angeles Rams" / "No. 1 Los Angeles Rams"
_NUM_THEN_TEAM = re.compile(r"^(?:no\.?\s*)?(\d{1,2})\s*[.):\-–]?\s+(.{2,60})$", re.I)


def from_headings(markup: str) -> list[tuple[int, str]]:
    out = []
    for _, inner in _HEADING.findall(markup):
        line = to_text(inner).replace("\n", " ").strip()
        m = _NUM_THEN_TEAM.match(line)
        if not m:
            continue
        abbr = find_in_text(m.group(2))
        if abbr:
            out.append((int(m.group(1)), abbr))
    return out


def from_numbered_lines(text: str) -> list[tuple[int, str]]:
    out = []
    for line in text.split("\n"):
        if len(line) > 70:
            continue
        m = _NUM_THEN_TEAM.match(line)
        if not m:
            continue
        abbr = resolve(m.group(2)) or find_in_text(m.group(2))
        if abbr:
            out.append((int(m.group(1)), abbr))
    return out


def from_rank_label_lines(text: str) -> list[tuple[int, str]]:
    """NFL.com style: a bare "Rank" line, then the number, then the team."""
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines[:-2]):
        if line.strip().lower() not in {"rank", "rk", "ranking"}:
            continue
        num, team = lines[i + 1].strip(), lines[i + 2].strip()
        if not num.isdigit():
            continue
        abbr = resolve(team) or find_in_text(team)
        if abbr:
            out.append((int(num), abbr))
    return out


def from_split_lines(text: str) -> list[tuple[int, str]]:
    """Table style: a line that is just the rank, then a line with the team."""
    lines = [ln.strip() for ln in text.split("\n")]
    out = []
    for i, line in enumerate(lines):
        if not (line.isdigit() and 1 <= int(line) <= 32):
            continue
        for nxt in lines[i + 1 : i + 3]:
            if len(nxt) > 45:
                break
            abbr = resolve(nxt)
            if abbr:
                out.append((int(line), abbr))
                break
    return out


def from_bare_sequence(text: str) -> list[tuple[int, str]]:
    """Last resort: 32 team names in order with no usable rank numbers."""
    seen: list[str] = []
    for line in text.split("\n"):
        if len(line) > 60:
            continue
        abbr = resolve(line.strip())
        if abbr and abbr not in seen:
            seen.append(abbr)
    return [(i + 1, a) for i, a in enumerate(seen)]


STRATEGIES = (
    ("headings", lambda markup, text: from_headings(markup)),
    ("rank-label", lambda markup, text: from_rank_label_lines(text)),
    ("numbered-lines", lambda markup, text: from_numbered_lines(text)),
    ("split-lines", lambda markup, text: from_split_lines(text)),
    ("bare-sequence", lambda markup, text: from_bare_sequence(text)),
)


def extract(markup: str) -> tuple[dict[str, int], str]:
    """Return (ranks, strategy_name) or raise RankParseError."""
    text = to_text(markup)
    errors = []
    for name, fn in STRATEGIES:
        try:
            pairs = fn(markup, text)
        except Exception as exc:  # a broken strategy must not kill the rest
            errors.append(f"{name}: {exc}")
            continue
        if not pairs:
            errors.append(f"{name}: no candidates")
            continue
        try:
            return validate(pairs), name
        except RankParseError as exc:
            errors.append(f"{name}: {exc}")
    raise RankParseError("; ".join(errors))
