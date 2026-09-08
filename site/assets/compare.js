import {
  loadIndex, loadSeason, latestWeek, chip, movement, fmtDate, initTheme,
  renderNav, rankChart, shortName, signed, readable,
} from './app.js';

const $ = id => document.getElementById(id);
initTheme($('theme'));

const st = { data: null, week: null, a: 'LAR', b: 'SEA' };

boot().catch(err => { $('cmp').innerHTML = `<tr><td class="empty">${err.message}</td></tr>`; });

async function boot() {
  const url = new URL(location.href);
  const idx = await loadIndex();
  const seasons = idx.seasons.map(s => s.season);
  const asked = Number(url.searchParams.get('season'));
  const season = seasons.includes(asked) ? asked : idx.default_season;
  $('season').innerHTML = seasons.map(y => `<option value="${y}">${y} season</option>`).join('');
  $('season').value = season;
  $('season').onchange = e => { location.href = `compare.html?season=${e.target.value}`; };
  renderNav($('nav'), 'compare.html', season);

  const d = await loadSeason(season);
  st.data = d;
  const wantedWeek = Number(url.searchParams.get('week'));
  st.week = d.weeksBy[wantedWeek] ? wantedWeek : latestWeek(d);

  // Default to the two teams the outlets disagree about most — a more
  // interesting opening state than an arbitrary pair.
  const wk = d.weeksBy[st.week];
  const byRank = Object.entries(wk.teams).sort((x, y) => x[1].rank - y[1].rank);
  st.a = (url.searchParams.get('a') || byRank[0]?.[0] || 'LAR').toUpperCase();
  st.b = (url.searchParams.get('b') || byRank[1]?.[0] || 'SEA').toUpperCase();
  if (!d.teamsBy[st.a]) st.a = byRank[0][0];
  if (!d.teamsBy[st.b] || st.b === st.a) st.b = byRank[1][0];

  const opts = d.teams.map(t => `<option value="${t.abbr}">${t.name}</option>`).join('');
  $('teamA').innerHTML = opts; $('teamB').innerHTML = opts;
  $('teamA').onchange = e => { st.a = e.target.value; render(); };
  $('teamB').onchange = e => { st.b = e.target.value; render(); };
  $('swap').onclick = () => { [st.a, st.b] = [st.b, st.a]; render(); };

  $('week').innerHTML = d.weeks.slice().sort((x, y) => y.week - x.week)
    .map(w => `<option value="${w.week}">${w.label}</option>`).join('');
  $('week').value = st.week;
  $('week').onchange = e => { st.week = Number(e.target.value); render(); };
  $('prev').onclick = () => step(-1);
  $('next').onclick = () => step(1);
  addEventListener('resize', drawChart);
  $('theme').addEventListener('click', () => render());
  render();
}

function step(dir) {
  const ws = st.data.weeks.map(w => w.week).sort((a, b) => a - b);
  const i = ws.indexOf(st.week) + dir;
  if (i >= 0 && i < ws.length) { st.week = ws[i]; $('week').value = st.week; render(); }
}

function render() {
  const d = st.data, wk = d.weeksBy[st.week];
  const ws = d.weeks.map(w => w.week).sort((a, b) => a - b);
  $('prev').disabled = st.week === ws[0];
  $('next').disabled = st.week === ws[ws.length - 1];
  $('teamA').value = st.a; $('teamB').value = st.b;
  history.replaceState(null, '', `?season=${d.season}&week=${st.week}&a=${st.a}&b=${st.b}`);
  $('meta').innerHTML = `${wk.sources.length} outlet${wk.sources.length === 1 ? '' : 's'}` +
    ` &middot; ${wk.games_through ? 'through Week ' + wk.games_through : 'preseason'}`;
  $('stamp').textContent = `Data compiled ${fmtDate(d.generated)}.`;
  $('cmpTitle').textContent = `${d.teamsBy[st.a].nickname} vs ${d.teamsBy[st.b].nickname} — ${wk.label}`;

  side('sideA', st.a); side('sideB', st.b);
  renderRows(wk);
  renderH2H();
  drawChart();
}

function side(id, abbr) {
  const d = st.data, t = d.teamsBy[abbr], e = d.weeksBy[st.week].teams[abbr];
  const host = $(id);
  host.textContent = '';
  host.style.borderTop = `3px solid ${t.primary}`;
  const top = document.createElement('div');
  top.className = 'top';
  top.appendChild(chip(t, 38));
  const h = document.createElement('div');
  h.innerHTML = `<h2>${t.nickname}</h2><div class="sub">${t.division} · ${e.record}</div>`;
  top.appendChild(h);
  host.appendChild(top);
  const line = document.createElement('div');
  line.style.cssText = 'display:flex;align-items:center;gap:9px;margin-top:11px';
  line.innerHTML = `<b style="font-family:var(--mono);font-size:26px">#${e.rank}</b>`;
  line.appendChild(movement(e.delta));
  line.insertAdjacentHTML('beforeend',
    `<span style="color:var(--muted);font-size:12.5px">score ${e.avg.toFixed(2)}</span>`);
  host.appendChild(line);
}

/* Rows are (label, valueA, valueB, betterSide) — "better" is what wins the row. */
function renderRows(wk) {
  const d = st.data;
  const A = wk.teams[st.a], B = wk.teams[st.b];
  const lower = (x, y) => (x == null || y == null) ? 0 : (x < y ? -1 : x > y ? 1 : 0);
  const higher = (x, y) => -lower(x, y);

  const rows = [
    ['Superpower rank', A.rank, B.rank, lower(A.rank, B.rank), v => `#${v}`],
    ['Score (avg rank)', A.avg, B.avg, lower(A.avg, B.avg), v => v.toFixed(2)],
    ['Record', A.record, B.record, 0, v => v],
    ['Rank by record', A.record_rank, B.record_rank, lower(A.record_rank, B.record_rank), v => v ? `#${v}` : '–'],
    ['Point differential', A.differential, B.differential, higher(A.differential, B.differential),
      v => (v > 0 ? '+' : '') + v],
    ['Best outlet rank', A.high, B.high, lower(A.high, B.high), v => `#${v}`],
    ['Worst outlet rank', A.low, B.low, lower(A.low, B.low), v => `#${v}`],
    ['Outlet spread', A.spread, B.spread, lower(A.spread, B.spread), v => `${v} spots`],
    ['Remaining SOS', A.sos_remaining, B.sos_remaining, lower(A.sos_remaining, B.sos_remaining),
      v => v != null ? v.toFixed(1) : '–'],
  ];
  if (A.market_rank || B.market_rank) {
    rows.push(['Market rank', A.market_rank, B.market_rank, lower(A.market_rank, B.market_rank),
      v => v ? `#${v}` : '–']);
    rows.push(['Super Bowl odds', A.market_odds, B.market_odds, 0, v => v || '–']);
  }
  for (const s of wk.sources) {
    rows.push([shortName(s.name), A.ranks[s.id], B.ranks[s.id],
      lower(A.ranks[s.id], B.ranks[s.id]), v => v != null ? `#${v}` : '–']);
  }

  const frag = document.createDocumentFragment();
  for (const [label, va, vb, better, fmt] of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="l${better < 0 ? ' win' : ''}" style="width:38%">${va == null ? '–' : fmt(va)}</td>
      <td class="mid">${label}</td>
      <td class="l${better > 0 ? ' win' : ''}" style="width:38%">${vb == null ? '–' : fmt(vb)}</td>`;
    if (better < 0) tr.children[0].style.color = readable(d.teamsBy[st.a].primary);
    if (better > 0) tr.children[2].style.color = readable(d.teamsBy[st.b].primary);
    frag.appendChild(tr);
  }
  $('cmp').textContent = '';
  $('cmp').appendChild(frag);
}

function renderH2H() {
  const d = st.data;
  const games = (d.games[st.a] || []).filter(g => g.opponent === st.b);
  if (!games.length) {
    $('h2h').innerHTML =
      `<tr><td class="empty" colspan="4">These two don't meet this season.</td></tr>`;
    return;
  }
  $('h2h').innerHTML = games.map(g => {
    const home = g.home ? st.a : st.b, away = g.home ? st.b : st.a;
    const played = g.completed && g.points_for != null;
    const score = played
      ? (g.home ? `${g.points_for}–${g.points_against}` : `${g.points_against}–${g.points_for}`)
      : `<span style="color:var(--muted)">${g.detail || 'not played yet'}</span>`;
    const res = played
      ? `<span class="res ${g.result}">${d.teamsBy[st.a].abbr} ${g.result}</span>`
      : '<span style="color:var(--muted)">–</span>';
    return `<tr><td class="l">${g.label}</td>
      <td class="l">${d.teamsBy[away].nickname} at ${d.teamsBy[home].nickname}</td>
      <td>${res}</td><td class="num">${score}</td></tr>`;
  }).join('');
}

function drawChart() {
  const d = st.data;
  const xs = d.weeks.map(w => w.week).sort((a, b) => a - b);
  const series = [st.a, st.b].map(abbr => ({
    label: d.teamsBy[abbr].nickname,
    color: readable(d.teamsBy[abbr].primary),
    width: 2.6, dots: true,
    points: xs.map(x => ({ x, y: d.weeksBy[x].teams[abbr]?.rank ?? null })),
  }));
  rankChart($('chart'), series, { xs, yMax: 32, height: 300 });
}
