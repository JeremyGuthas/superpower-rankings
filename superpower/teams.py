"""Canonical NFL team registry plus alias matching.

Every outlet writes team names differently ("LA Rams", "L.A. Rams", "Rams",
"Los Angeles Rams"). Everything upstream normalises through `resolve()`.
"""
from __future__ import annotations

import re
import unicodedata

# abbr: (location, nickname, conference, division, primary, secondary)
TEAMS: dict[str, tuple] = {
    "ARI": ("Arizona", "Cardinals", "NFC", "West", "#97233F", "#FFB612"),
    "ATL": ("Atlanta", "Falcons", "NFC", "South", "#A71930", "#000000"),
    "BAL": ("Baltimore", "Ravens", "AFC", "North", "#241773", "#9E7C0C"),
    "BUF": ("Buffalo", "Bills", "AFC", "East", "#00338D", "#C60C30"),
    "CAR": ("Carolina", "Panthers", "NFC", "South", "#0085CA", "#101820"),
    "CHI": ("Chicago", "Bears", "NFC", "North", "#0B162A", "#C83803"),
    "CIN": ("Cincinnati", "Bengals", "AFC", "North", "#FB4F14", "#000000"),
    "CLE": ("Cleveland", "Browns", "AFC", "North", "#311D00", "#FF3C00"),
    "DAL": ("Dallas", "Cowboys", "NFC", "East", "#003594", "#869397"),
    "DEN": ("Denver", "Broncos", "AFC", "West", "#FB4F14", "#002244"),
    "DET": ("Detroit", "Lions", "NFC", "North", "#0076B6", "#B0B7BC"),
    "GB":  ("Green Bay", "Packers", "NFC", "North", "#203731", "#FFB612"),
    "HOU": ("Houston", "Texans", "AFC", "South", "#03202F", "#A71930"),
    "IND": ("Indianapolis", "Colts", "AFC", "South", "#002C5F", "#A2AAAD"),
    "JAX": ("Jacksonville", "Jaguars", "AFC", "South", "#006778", "#D7A22A"),
    "KC":  ("Kansas City", "Chiefs", "AFC", "West", "#E31837", "#FFB81C"),
    "LAC": ("Los Angeles", "Chargers", "AFC", "West", "#0080C6", "#FFC20E"),
    "LAR": ("Los Angeles", "Rams", "NFC", "West", "#003594", "#FFA300"),
    "LV":  ("Las Vegas", "Raiders", "AFC", "West", "#000000", "#A5ACAF"),
    "MIA": ("Miami", "Dolphins", "AFC", "East", "#008E97", "#FC4C02"),
    "MIN": ("Minnesota", "Vikings", "NFC", "North", "#4F2683", "#FFC62F"),
    "NE":  ("New England", "Patriots", "AFC", "East", "#002244", "#C60C30"),
    "NO":  ("New Orleans", "Saints", "NFC", "South", "#101820", "#D3BC8D"),
    "NYG": ("New York", "Giants", "NFC", "East", "#0B2265", "#A71930"),
    "NYJ": ("New York", "Jets", "AFC", "East", "#125740", "#000000"),
    "PHI": ("Philadelphia", "Eagles", "NFC", "East", "#004C54", "#A5ACAF"),
    "PIT": ("Pittsburgh", "Steelers", "AFC", "North", "#FFB612", "#101820"),
    "SEA": ("Seattle", "Seahawks", "NFC", "West", "#002244", "#69BE28"),
    "SF":  ("San Francisco", "49ers", "NFC", "West", "#AA0000", "#B3995D"),
    "TB":  ("Tampa Bay", "Buccaneers", "NFC", "South", "#D50A0A", "#FF7900"),
    "TEN": ("Tennessee", "Titans", "AFC", "South", "#0C2340", "#4B92DB"),
    "WSH": ("Washington", "Commanders", "NFC", "East", "#5A1414", "#FFB612"),
}

# Extra spellings outlets actually use. Nicknames and full names are generated.
EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "ARI": ("arizona", "cards", "az cardinals"),
    "BAL": ("baltimore",),
    "CAR": ("carolina",),
    "CIN": ("cincinnati", "cincy"),
    "CLE": ("cleveland",),
    "GB": ("gnb", "green bay", "packers", "green bay packers"),
    "HOU": ("houston",),
    "IND": ("indianapolis", "indy"),
    "JAX": ("jac", "jacksonville", "jags"),
    "KC": ("kan", "kansas city", "kc chiefs"),
    "LAC": ("sd", "sdg", "san diego chargers", "la chargers", "l.a. chargers",
            "los angeles chargers", "lachargers"),
    "LAR": ("stl", "st. louis rams", "la rams", "l.a. rams",
            "los angeles rams", "larams"),
    "LV": ("oak", "oakland raiders", "las vegas", "vegas", "raiders"),
    "NE": ("nwe", "new england", "pats"),
    "NO": ("nor", "new orleans"),
    "NYG": ("new york giants", "ny giants", "g-men"),
    "NYJ": ("new york jets", "ny jets"),
    "PHI": ("philadelphia", "philly"),
    "PIT": ("pittsburgh",),
    "SEA": ("seattle",),
    "SF": ("sfo", "san francisco", "niners", "49ers", "san francisco 49ers"),
    "TB": ("tam", "tampa bay", "tampa", "bucs", "buccaneers"),
    "TEN": ("tennessee",),
    "WSH": ("was", "wsh", "washington", "commanders", "washington commanders",
            "washington football team", "redskins"),
}

# All 32 nicknames are unique inside the NFL, so a bare nickname always
# resolves. The real ambiguity is shared cities ("Los Angeles", "New York"),
# which is why bare locations are never registered as aliases.


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    # "N.Y. Giants" -> "n y giants" -> "ny giants"; same for "L.A.", "T.B.".
    return re.sub(r"\b([a-z]) (?=[a-z]\b)", r"\1", s)


def _build_alias_map() -> dict[str, str]:
    out: dict[str, str] = {}

    def put(alias: str, abbr: str) -> None:
        key = _norm(alias)
        if key and key not in out:
            out[key] = abbr

    for abbr, (loc, nick, *_rest) in TEAMS.items():
        put(abbr, abbr)
        put(f"{loc} {nick}", abbr)
        put(nick, abbr)
        for alias in EXTRA_ALIASES.get(abbr, ()):
            put(alias, abbr)
    return out


ALIASES = _build_alias_map()

# Longest-first so "Los Angeles Rams" wins over "Rams" when both could match.
# Two- and three-letter abbreviations are ordinary English words ("no", "ne",
# "gb"), so they are matched only when a whole field is the team — never
# inside prose. Losing "KC" in a sentence costs little; reading "No Rank
# change" as the Saints corrupts a whole ranking.
_PROSE_ALIASES = sorted(
    (a for a in ALIASES if len(a) > 3),
    key=len,
    reverse=True,
)
_PROSE_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(a) for a in _PROSE_ALIASES) + r")(?![a-z0-9])"
)


def resolve(name: str) -> str | None:
    """Map an outlet's team string to a canonical abbreviation."""
    if not name:
        return None
    key = _norm(name)
    if key in ALIASES:
        return ALIASES[key]
    # Strip trailing seeding/record noise: "Buffalo Bills (2-0)".
    key = re.sub(r"\s*\(.*?\)\s*$", "", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    m = _PROSE_RE.search(key)
    return ALIASES[m.group(1)] if m else None


def resolve_exact(name: str) -> str | None:
    """Resolve only when the whole string names a team.

    Used wherever a field is expected to *be* a team name — a table cell, a
    heading, the line after a rank number. Unlike `resolve`, it never scans
    for a team mentioned inside other words.
    """
    if not name:
        return None
    key = _norm(name)
    if key in ALIASES:
        return ALIASES[key]
    key = re.sub(r"\s*\(.*?\)\s*$", "", key).strip()
    return ALIASES.get(key)


def find_in_text(text: str) -> str | None:
    """Resolve the first team mentioned anywhere in a line of prose."""
    m = _PROSE_RE.search(_norm(text))
    return ALIASES[m.group(1)] if m else None


def info(abbr: str) -> dict:
    loc, nick, conf, div, primary, secondary = TEAMS[abbr]
    return {
        "abbr": abbr,
        "location": loc,
        "nickname": nick,
        "name": f"{loc} {nick}",
        "conference": conf,
        "division": f"{conf} {div}",
        "primary": primary,
        "secondary": secondary,
        "slug": _norm(f"{loc} {nick}").replace(" ", "-"),
    }


def all_teams() -> list[dict]:
    return [info(a) for a in sorted(TEAMS)]
