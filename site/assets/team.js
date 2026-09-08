import {
  loadIndex, loadSeason, latestWeek, movement, fmtDate, initTheme, rankChart,
  OUTLET_COLORS, shortName, renderNav, gapChip, signed, chip,
} from './app.js';

const $ = id => document.getElementById(id);
initTheme($('theme'));

const state = { data: null, abbr: null, week: null, show: new Set() };

boot().catch(err => { $('heroName').textContent = err.message; });

async function boot() {
  const url = new URL(location.href);
  const idx = await loadIndex();
  const seasons = idx.seasons.map(s => s.season);
  const asked = Number(url.searchParams.get('season'));
  const season = seasons.includes(asked) ? asked : idx.default_season;
  $('season').innerHTML = seasons.map(y => `<option value="${y}">${y}</option>`).join('');
  $('season').value = season;
  $('season').onchange = e => {
    location.href = `team.html?season=${e.target.value}&t=${state.abbr}`;
  };

  renderNav($('nav'), '', season);
  const data = await loadSeason(season);
  state.data = data;
  state.abbr = (url.searchParams.get('t') || 'LAR').toUpperCase();
  if (!data.teamsBy[state.abbr]) state.abbr = data.teams[0].abbr;
  const askedWeek = Number(url.searchParams.get('week'));
  state.week = data.weeksBy[askedWeek] ? askedWeek : latestWeek(data);

  $('week').innerHTML = data.weeks.slice().sort((a, b) => b.week - a.week)
    .map(w => `<option value="${w.week}">${w.label}</option>`).join('');
  $('week').value = state.week;
  $('teamPick').innerHTML = data.teams
    .map(t => `<option value="${t.abbr}">${t.name}</option>`).join('');
  $('teamPick').value = state.abbr;

  $('week').onchange = e => { state.week = Number(e.target.value); render(); };
  $('teamPick').onchange = e => { state.abbr = e.target.value; render(); };
  $('prev').onclick = () => step(-1);
  $('next').onclick = () => step(+1);
  addEventListener('resize', () => drawChart());
  render();
}

function step(dir) {
  const weeks = state.data.weeks.map(w => w.week).sort((a, b) => a - b);
  const i = weeks.indexOf(state.week) + dir;
  if (i >= 0 && i < weeks.length) { state.week = weeks[i]; $('week').value = state.week; render(); }
}

const entry = (wk, abbr) => wk.teams[abbr];

function render() {
  const d = state.data, abbr = state.abbr;
  const team = d.teamsBy[abbr];
  const wk = d.weeksBy[state.week];
  const t = entry(wk, abbr);
  const weeks = d.weeks.map(w => w.week).sort((a, b) => a - b);
  $('prev').disabled = state.week === weeks[0];
  $('next').disabled = state.week === weeks[weeks.length - 1];
  history.replaceState(null, '', `?season=${d.season}&t=${abbr}&week=${state.week}`);
  document.title = `${team.name} — Superpower Rankings`;
  $('teamPick').value = abbr;

  // hero
  $('hero').style.background =
    `linear-gradient(100deg, ${team.primary} 0%, ${team.primary} 58%, ${team.secondary} 190%)`;
  $('heroChip').textContent = team.abbr;
  $('heroName').textContent = team.name;
  const through = wk.games_through
    ? `${t.record} through Week ${wk.games_through}` : 'preseason';
  $('heroSub').textContent = `${team.division} · ${through} · ${d.season} ${wk.label}`;

  const all = d.weeks.map(w => entry(w, abbr)?.rank).filter(Boolean);
  $('heroStats').innerHTML = `
    <div><b>#${t.rank}</b><span>Superpower</span></div>
    <div><b>${t.avg.toFixed(2)}</b><span>Score</span></div>
    <div><b>${t.high}–${t.low}</b><span>Outlet high/low</span></div>
    <div><b>${Math.min(...all)}</b><span>Season best</span></div>`;
  $('meta').innerHTML = `${wk.sources.length} outlet${wk.sources.length === 1 ? '' : 's'}` +
    ` &middot; updated ${fmtDate(wk.generated)}`;
  $('stamp').textContent = `Data compiled ${fmtDate(d.generated)}.`;

  // default: show consensus only, plus any outlet the reader toggled on
  const outletIds = d.sources.map(s => s.id);
  if (!state.legendReady) {
    $('legend').innerHTML = '';
    $('legend').appendChild(legendBtn('consensus', 'Superpower', 'var(--ink)', true));
    outletIds.forEach((id, i) => $('legend').appendChild(
      legendBtn(id, d.sourcesBy[id].name, OUTLET_COLORS[i % OUTLET_COLORS.length], false)));
    state.show.add('consensus');
    state.legendReady = true;
  }

  $('compareLink').href = `compare.html?season=${d.season}&week=${state.week}&a=${abbr}`;
  renderContext(wk, t, d, team);
  renderOutlets(wk, t, d);
  renderGames(d, abbr);
  renderWeekByWeek(d, abbr, outletIds);
  drawChart();
}

function legendBtn(id, label, color, on) {
  const b = document.createElement('button');
  b.type = 'button';
  b.setAttribute('aria-pressed', String(on));
  b.innerHTML = `<span class="swatch" style="background:${color}"></span>${label}`;
  b.onclick = () => {
    const now = b.getAttribute('aria-pressed') === 'true';
    b.setAttribute('aria-pressed', String(!now));
    if (now) state.show.delete(id); else state.show.add(id);
    drawChart();
  };
  b.dataset.color = color;
  return b;
}

function drawChart() {
  const d = state.data, abbr = state.abbr;
  const xs = d.weeks.map(w => w.week).sort((a, b) => a - b);
  const series = [];
  d.sources.forEach((s, i) => {
    if (!state.show.has(s.id)) return;
    series.push({
      id: s.id, label: s.name,
      color: OUTLET_COLORS[i % OUTLET_COLORS.length], width: 1.6, opacity: .85, dash: '4 3',
      points: xs.map(x => ({ x, y: entry(d.weeksBy[x], abbr)?.ranks?.[s.id] ?? null })),
    });
  });
  if (state.show.has('consensus')) {
    series.push({
      id: 'consensus', label: 'Superpower',
      color: getComputedStyle(document.body).getPropertyValue('--ink').trim() || '#111',
      width: 2.75, dots: true,
      points: xs.map(x => ({ x, y: entry(d.weeksBy[x], abbr)?.rank ?? null })),
    });
  }
  rankChart($('chart'), series, { xs, yMax: 32, height: 300 });
}

function renderOutlets(wk, t, d) {
  $('outletTitle').textContent = `Outlet by outlet — ${wk.label}`;
  const rows = wk.sources.map(s => {
    const r = t.ranks[s.id];
    const dlt = t.source_delta?.[s.id];
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="l">${s.name}</td>
      <td class="score">${r ?? '–'}</td><td></td>
      <td class="l"><a href="${s.url}" target="_blank" rel="noopener"
        style="text-decoration:underline;text-underline-offset:2px">Article ↗</a></td>`;
    tr.children[2].appendChild(movement(dlt ?? null, { newLabel: '—' }));
    return tr;
  });
  $('outlets').textContent = '';
  rows.forEach(r => $('outlets').appendChild(r));
}

function renderGames(d, abbr) {
    const log = withByes(d.games[abbr] || []);
  const rankAfter = g => {
    // Rankings published after week W's games carry the label "week W+1".
    // Playoff rounds reuse week numbers 1-5, so they must never map across.
    if (g.season_type !== 'regular') return null;
    return (d.weeksBy[g.week + 1] && entry(d.weeksBy[g.week + 1], abbr)) || null;
  };
  $('recordPill').textContent = `Season ${summarise(log)}`;
  if (!log.length) {
    $('games').innerHTML = `<tr><td class="empty" colspan="6">No games played yet.</td></tr>`;
    return;
  }
  const frag = document.createDocumentFragment();
  for (const g of log) {
    if (g.bye) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="l">${g.label}</td>
        <td class="l" style="color:var(--muted)">Bye week</td>
        <td colspan="4"></td>`;
      frag.appendChild(tr);
      continue;
    }
    const opp = d.teamsBy[g.opponent];
    const tr = document.createElement('tr');
    const margin = g.points_for != null && g.points_against != null
      ? g.points_for - g.points_against : null;
    const after = rankAfter(g);
    tr.innerHTML = `
      <td class="l">${g.label}</td>
      <td class="l"><a class="team" href="team.html?season=${d.season}&t=${g.opponent}">
        <span class="chip" style="background:${opp.primary};width:20px;height:20px;flex-basis:20px;font-size:8px">${opp.abbr}</span>
        <span>${g.home ? '' : '@ '}${opp.nickname}</span></a></td>
      <td>${g.result ? `<span class="res ${g.result}">${g.result}</span>` : '<span style="color:var(--muted)">–</span>'}</td>
      <td>${g.points_for != null ? `${g.points_for}–${g.points_against}` : '<span style="color:var(--muted)">' + (g.detail || 'TBD') + '</span>'}</td>
      <td>${margin != null ? (margin > 0 ? '+' : '') + margin : ''}</td>
      <td class="l"></td>`;
    if (after) {
      const box = document.createElement('span');
      box.style.cssText = 'display:inline-flex;align-items:center;gap:6px';
      box.insertAdjacentHTML('beforeend', `<b>#${after.rank}</b>`);
      box.appendChild(movement(after.delta));
      tr.lastElementChild.appendChild(box);
    } else {
      tr.lastElementChild.innerHTML = '<span style="color:var(--muted)">–</span>';
    }
    frag.appendChild(tr);
  }
  $('games').textContent = '';
  $('games').appendChild(frag);
}

/** Insert an explicit Bye row for any regular-season week with no game. */
function withByes(log) {
  const regular = log.filter(g => g.season_type === 'regular');
  const post = log.filter(g => g.season_type !== 'regular');
  if (!regular.length) return log;
  const last = Math.max(...regular.map(g => g.week));
  const have = new Set(regular.map(g => g.week));
  const out = [];
  for (let w = 1; w <= last; w++) {
    if (have.has(w)) out.push(regular.find(g => g.week === w));
    else out.push({ bye: true, week: w, label: `Week ${w}`, season_type: 'regular' });
  }
  return out.concat(post);
}

function summarise(log) {
  let w = 0, l = 0, t = 0;
  for (const g of log) {
    if (g.bye || g.season_type !== 'regular' || !g.completed) continue;
    if (g.result === 'W') w++; else if (g.result === 'L') l++; else if (g.result === 'T') t++;
  }
  return `${w}-${l}${t ? '-' + t : ''}`;
}

function renderWeekByWeek(d, abbr, outletIds) {
  $('wbwHead').innerHTML = `<th class="l">Week</th><th>Superpower</th><th>Move</th><th>Score</th>` +
    outletIds.map(id => `<th class="src">${shortName(d.sourcesBy[id].name)}</th>`).join('');
  const frag = document.createDocumentFragment();
  for (const w of d.weeks.slice().sort((a, b) => b.week - a.week)) {
    const t = entry(w, abbr);
    if (!t) continue;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="l">${w.label}</td><td class="rk" style="font-size:14px">${t.rank}</td>
      <td></td><td class="score">${t.avg.toFixed(2)}</td>` +
      outletIds.map(id => `<td class="src">${t.ranks[id] ?? '–'}</td>`).join('');
    tr.children[2].appendChild(movement(t.delta));
    frag.appendChild(tr);
  }
  $('wbw').textContent = '';
  $('wbw').appendChild(frag);
}


/* ---- season context: forward-looking, and where the team is contested ---- */

function renderContext(wk, t, d, team) {
  const card = (title, main, sub) => {
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `<h3>${title}</h3>`;
    const big = document.createElement('div');
    big.className = 'big';
    if (typeof main === 'string') big.innerHTML = main; else big.appendChild(main);
    el.appendChild(big);
    el.insertAdjacentHTML('beforeend', `<div class="sub">${sub}</div>`);
    return el;
  };

  const cards = [];

  const ng = t.next_game;
  if (ng) {
    const opp = d.teamsBy[ng.opponent];
    const row = document.createElement('span');
    row.style.cssText = 'display:inline-flex;align-items:center;gap:8px';
    row.insertAdjacentHTML('beforeend',
      `<span style="color:var(--muted);font-weight:600">${ng.home ? 'vs' : '@'}</span>`);
    row.appendChild(chip(opp, 22));
    row.insertAdjacentHTML('beforeend',
      `<a href="team.html?season=${d.season}&t=${ng.opponent}">${opp.nickname}</a>`);
    cards.push(card('Next up', row,
      `${ng.label}${ng.opponent_rank ? ` &middot; opponent ranked #${ng.opponent_rank}` : ''}`));
  } else {
    cards.push(card('Next up', '<span style="color:var(--muted)">Season complete</span>',
      'No fixtures remaining'));
  }

  cards.push(card('Remaining schedule',
    t.sos_remaining != null
      ? `<span class="score">${t.sos_remaining.toFixed(1)}</span>`
      : '<span style="color:var(--muted)">–</span>',
    t.sos_rank
      ? `${ordinalish(t.sos_rank)} toughest of 32 &middot; ${t.opponents_remaining} to play`
      : 'Average Superpower rank of remaining opponents'));

  const rec = document.createElement('span');
  rec.style.cssText = 'display:inline-flex;align-items:center;gap:8px';
  rec.innerHTML = t.record_rank
    ? `<span class="score">#${t.record_rank}</span>` : '<span style="color:var(--muted)">–</span>';
  if (t.divergence != null) rec.appendChild(gapChip(t.divergence));
  cards.push(card('By record alone', rec,
    t.divergence == null ? 'Available once games are played'
      : t.divergence > 0
        ? `Ranked ${Math.abs(t.divergence)} spots better than results justify`
        : t.divergence < 0
          ? `Ranked ${Math.abs(t.divergence)} spots below what results justify`
          : 'Ranking and results agree exactly'));

  if (t.market_rank) {
    const mk = document.createElement('span');
    mk.style.cssText = 'display:inline-flex;align-items:center;gap:8px';
    mk.innerHTML = `<span class="score">${t.market_odds}</span>`;
    if (t.market_gap != null) mk.appendChild(gapChip(t.market_gap));
    const pct = t.market_probability != null
      ? ` &middot; ${(t.market_probability * 100).toFixed(1)}% to win it all` : '';
    cards.push(card('Super Bowl market', mk, `Market rank #${t.market_rank}${pct}`));
  }

  $('context').textContent = '';
  cards.slice(0, 4).forEach(c => $('context').appendChild(c));

  const o = t.outlier;
  const note = $('outlierNote');
  if (o) {
    const outlet = d.sourcesBy[o.source]?.name || o.source;
    const side = o.gap > 0 ? 'higher' : 'lower';
    note.style.display = '';
    note.innerHTML = `<b>${outlet} is the outlier on ${team.name}.</b> They have them at
      <b>#${o.rank}</b> — ${Math.abs(o.gap)} spots ${side} than the consensus at #${t.rank},
      the widest gap any single outlet has on this team.`;
  } else {
    note.style.display = 'none';
  }
}

const ordinalish = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10]
  || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');
