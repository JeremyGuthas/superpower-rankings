# ⚡ Superpower Rankings

Every major NFL power ranking, averaged into one consensus board — updated
automatically every Tuesday, with a full week-by-week archive and a page for
each team.

```
superpower-rankings/
├── superpower/          the aggregator (fetch → parse → validate → average)
│   ├── sources/         one adapter per outlet
│   ├── extract.py       turns an article into a validated 1-32 ranking
│   ├── aggregate.py     the Superpower Score
│   ├── games.py         schedule, scores and records
│   └── season.py        the ranking-week calendar
├── site/                the static website (no build step)
├── data/                generated JSON — the site reads this
├── snapshot/            bundles the whole site into one shareable HTML file
├── tests/               43 tests over the parts that break silently
└── .github/workflows/   the Tuesday cron
```

## Quick start

```bash
pip install -r requirements.txt
python -m superpower.run --verbose
python -m http.server 8777       # then open http://localhost:8777/site/
```

## How the ranking is built

1. **Find this week's article** for each outlet. Some outlets keep rankings on
   one permanent URL; others publish a new article weekly, which is discovered
   from their homepage, section page or RSS feed.
2. **Read all 32 teams out of it.** Four parsing strategies are tried in turn
   (numbered headings, "Rank / N / Team" blocks, numbered lines, rank-then-team
   table rows), plus a last-resort ordering pass.
3. **Validate before trusting.** A source only counts when it yields a complete,
   duplicate-free permutation of 1–32. Anything short of that is dropped for the
   week and shown on the site as a miss — the score is never built on a
   half-parsed list.
4. **Average.** A team's **Superpower Score** is the mean of its ranks. Lower is
   better. Ties break on median rank, then on the team's single best ranking.

Alongside the score the site records each team's high/low, the spread between
outlets (how divisive the team is), the standard deviation, and movement versus
last week — both overall and *within each individual outlet*.

### A note on the week numbers

Outlets label rankings by the **upcoming** week: the list published the Tuesday
after Week 1's games is "Week 2 Power Rankings". The calendar in
`superpower/season.py` follows that convention, and `games_through` records that
Week N's rankings react to games played through Week N−1. Records shown next to
a ranking are as of that point, which is why a Week 18 board shows a 13-3 team
whose full-season log reads 14-3.

## Sources

| Outlet | Discovery | Archive |
|---|---|---|
| ESPN | search API → story API | ✅ full season |
| NFL.com | homepage / news index | current week |
| CBS Sports | permanent rankings URL | current week |
| Sharp Football Analysis | permanent rankings URL | current week |
| Yahoo Sports | RSS + section page | current week |
| Bleacher Report | section page | current week |
| Sporting News, FOX Sports | best effort | current week |

ESPN is the only outlet with an addressable archive, so `--backfill` on a past
season fills in from ESPN alone. **Outlets that publish to a single rolling URL
are deliberately excluded from backfill** — that page always shows *today's*
rankings, and filing it under an old week would silently fabricate history.

Rankings belong to their outlets. Every ranking on the site links back to the
original article, requests are rate-limited to one hit per host every 1.5s, and
responses are cached locally.

### Adding an outlet

Most outlets need one line in `superpower/sources/registry.py`:

```python
StaticPageSource(id="theringer", name="The Ringer",
                 url="https://www.theringer.com/nfl-power-rankings")
```

or, for one that publishes a new article each week:

```python
GenericSource(id="usatoday", name="USA Today",
              listings=("https://www.usatoday.com/sports/nfl/",),
              feeds=("https://rssfeeds.usatoday.com/nfl",),
              link_pattern=r'href="([^"]*nfl-power-rankings[^"]*)"')
```

Then check it: `python -m superpower.run --only usatoday --verbose`.
If the shared extractor can't read the page, write a small adapter subclassing
`Source` — see `sources/espn.py` for the pattern.

## Automatic updates

`.github/workflows/update.yml` runs every **Tuesday at 16:00 and 20:00 UTC**
(noon and 4pm ET), commits any changed data, and redeploys the site to GitHub
Pages. The second run catches outlets that publish late; because sources are
validated independently, a late outlet simply joins the average when it appears.

To run it anywhere else, the same command on a cron works:

```cron
0 12,16 * * 2  cd /path/to/superpower-rankings && python -m superpower.run
```

## CLI

```bash
python -m superpower.run                      # current season, current week
python -m superpower.run --week 5             # a specific week
python -m superpower.run --season 2025 --week 18 --backfill
python -m superpower.run --only espn cbs      # test one or two sources
python -m superpower.run --exclude yahoo
python -m superpower.run --compile-only       # rebuild site data, no fetching
```

## One-file snapshot

To hand someone the whole site as a single file — every season's data, styles and
script inlined — build a snapshot:

```bash
python snapshot/build.py --standalone      # -> dist/superpower-rankings.html
```

It opens straight off disk with no server. It is a snapshot, not the live site:
it shows the data as of the moment it was built and will not update itself.

## Tests

```bash
python -m pytest tests/ -q
```

They cover team-name matching (every alias every outlet uses), each extraction
strategy, the rejection of incomplete or duplicated rankings, the Tuesday
calendar rollover, the averaging and tie-breaks, movement deltas, and the
guard that keeps rolling-URL sources out of backfilled history.
