const D = window.__SPR__;
const $ = id => document.getElementById(id);
const S = {};   // per-season indexes
for (const [yr, data] of Object.entries(D.seasons)) {
  data.teamsBy   = Object.fromEntries(data.teams.map(t => [t.abbr, t]));
  data.sourcesBy = Object.fromEntries(data.sources.map(s => [s.id, s]));
  data.weeksBy   = Object.fromEntries(data.weeks.map(w => [w.week, w]));
  S[yr] = data;
}

const st = { season: D.default_season, week: null, view: 'board',
             abbr: 'LAR', cols: true, filter: '', show: new Set(['consensus']) };
const d = () => S[st.season];
const wk = () => d().weeksBy[st.week];
const OUTLET_COLORS = ['#c9762f','#3f7cac','#7a5195','#2f8b6c','#b23a6b','#8a8730','#0f6f8f','#a3492a'];
const shortName = n => n.replace('Sharp Football Analysis','Sharp')
  .replace('Bleacher Report','B/R').replace(' Sports','');

/* theme */
try { const t = localStorage.getItem('spr-theme'); if (t) document.documentElement.dataset.theme = t; } catch {}
$('theme').onclick = () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('spr-theme', dark ? 'light' : 'dark'); } catch {}
  if (st.view === 'team') drawChart();
};

/* chrome */
$('season').innerHTML = Object.keys(S).sort((a,b)=>b-a)
  .map(y => `<option value="${y}">${y} season</option>`).join('');
$('season').value = st.season;
$('season').onchange = e => {
  st.season = e.target.value;
  st.week = Math.max(...d().weeks.map(w => w.week));
  fillWeeks(); render();
};
$('teamPick').innerHTML = d().teams.map(t => `<option value="${t.abbr}">${t.name}</option>`).join('');
$('teamPick').onchange = e => { st.abbr = e.target.value; render(); };
$('week').onchange = e => { st.week = +e.target.value; render(); };
$('prev').onclick = () => step(-1);
$('next').onclick = () => step(1);
$('cols').onchange = e => { st.cols = e.target.checked; render(); };
$('filter').onchange = e => { st.filter = e.target.value; render(); };
$('home').onclick = e => { e.preventDefault(); go('board'); };
$('navBoard').onclick = () => go('board');
$('navHow').onclick = () => { go('board'); $('how').scrollIntoView({ behavior: 'smooth' }); };
addEventListener('resize', () => { if (st.view === 'team') drawChart(); });

function fillWeeks() {
  $('week').innerHTML = d().weeks.slice().sort((a,b)=>b.week-a.week)
    .map(w => `<option value="${w.week}">${w.label}</option>`).join('');
  $('week').value = st.week;
}
function step(dir) {
  const ws = d().weeks.map(w => w.week).sort((a,b)=>a-b);
  const i = ws.indexOf(st.week) + dir;
  if (i >= 0 && i < ws.length) { st.week = ws[i]; $('week').value = st.week; render(); }
}
function go(view, abbr) {
  st.view = view;
  if (abbr) st.abbr = abbr;
  scrollTo({ top: 0 });
  render();
}

/* helpers */
function chip(team, size) {
  const el = document.createElement('span');
  el.className = 'chip';
  el.style.background = team.primary;
  el.style.boxShadow = `inset 0 0 0 1.5px ${team.secondary}`;
  el.textContent = team.abbr;
  if (size) el.style.width = el.style.height = el.style.flexBasis = size + 'px';
  const img = new Image();
  img.alt = ''; img.loading = 'lazy';
  img.src = `https://a.espncdn.com/i/teamlogos/nfl/500/${team.abbr.toLowerCase()}.png`;
  img.onerror = () => img.remove();
  el.appendChild(img);
  return el;
}
function teamLink(team, division = true) {
  const a = document.createElement('a');
  a.className = 'team'; a.href = '#';
  a.onclick = e => { e.preventDefault(); go('team', team.abbr); };
  a.appendChild(chip(team));
  const t = document.createElement('span');
  t.innerHTML = `<span class="nm">${team.name}</span>` +
    (division ? ` <span class="dv">${team.division}</span>` : '');
  a.appendChild(t);
  return a;
}
function movement(v, newLabel = 'NEW') {
  const el = document.createElement('span');
  if (v == null)      { el.className = 'mv new';  el.textContent = newLabel; }
  else if (v > 0)     { el.className = 'mv up';   el.textContent = `▲ ${v}`; }
  else if (v < 0)     { el.className = 'mv down'; el.textContent = `▼ ${-v}`; }
  else                { el.className = 'mv flat'; el.textContent = '–'; }
  return el;
}
const fmtDate = iso => {
  if (!iso) return '';
  const x = new Date(iso);
  return isNaN(x) ? '' : x.toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
};

/* render */
function render() {
  const ws = d().weeks.map(w => w.week).sort((a,b)=>a-b);
  if (!d().weeksBy[st.week]) st.week = ws[ws.length - 1];
  $('week').value = st.week;
  $('prev').disabled = st.week === ws[0];
  $('next').disabled = st.week === ws[ws.length - 1];
  $('stamp').innerHTML = `${wk().sources.length} outlet${wk().sources.length === 1 ? '' : 's'}` +
    ` &middot; ${wk().games_through ? 'through Week ' + wk().games_through : 'preseason'}`;
  $('snapshot').textContent =
    `Snapshot of the live site — data compiled ${fmtDate(d().generated)}.`;

  const team = st.view === 'team';
  $('viewBoard').classList.toggle('hidden', team);
  $('viewTeam').classList.toggle('hidden', !team);
  $('hero').classList.toggle('hidden', !team);
  $('teamPick').classList.toggle('hidden', !team);
  $('colsWrap').classList.toggle('hidden', team);
  $('filter').classList.toggle('hidden', team);
  team ? renderTeam() : renderBoard();
}

function renderBoard() {
  const w = wk(), data = d();
  $('boardTitle').textContent = `${data.season} ${w.label} Superpower Rankings`;
  $('srcCount').textContent = `${w.sources.length} outlet${w.sources.length === 1 ? '' : 's'}`;

  /* tiles */
  const n = w.notes || {};
  const byRank = Object.entries(w.teams).sort((a,b) => a[1].rank - b[1].rank);
  const top = byRank[0], bottom = byRank[byRank.length - 1];
  const used = new Set([top[0]]);
  if (n.biggest_riser) used.add(n.biggest_riser);
  if (n.biggest_faller) used.add(n.biggest_faller);
  const tightest = byRank.filter(([a]) => !used.has(a)).sort((a,b) => a[1].spread - b[1].spread)[0];
  const move = a => { const v = w.teams[a].delta; return v > 0 ? `up ${v}` : v < 0 ? `down ${-v}` : 'unchanged'; };

  const tile = (title, abbr, sub) => {
    if (!abbr) return null;
    const t = data.teamsBy[abbr];
    const el = document.createElement('div');
    el.className = 'tile';
    el.innerHTML = `<h3>${title}</h3>`;
    const row = document.createElement('div');
    row.className = 'row';
    row.appendChild(chip(t, 22));
    const a = document.createElement('a');
    a.href = '#'; a.innerHTML = `<b>${t.name}</b>`;
    a.onclick = e => { e.preventDefault(); go('team', abbr); };
    row.appendChild(a);
    el.appendChild(row);
    el.insertAdjacentHTML('beforeend', `<div class="sub">${sub}</div>`);
    return el;
  };

  const tiles = [tile('No. 1 overall', top[0], `Score ${top[1].avg} &middot; ${top[1].record}`)];
  if (n.biggest_riser && w.teams[n.biggest_riser].delta > 0) {
    tiles.push(tile('Biggest riser', n.biggest_riser, `${move(n.biggest_riser)} to #${w.teams[n.biggest_riser].rank}`));
    tiles.push(tile('Biggest faller', n.biggest_faller, `${move(n.biggest_faller)} to #${w.teams[n.biggest_faller].rank}`));
  } else {
    tiles.push(tile('No. 32 overall', bottom[0], `Score ${bottom[1].avg}`));
    if (tightest) tiles.push(tile('Tightest consensus', tightest[0],
      `Every outlet within ${tightest[1].spread} spot${tightest[1].spread === 1 ? '' : 's'}`));
  }
  if (w.sources.length > 1 && n.most_divisive) {
    tiles.push(tile('Most divisive', n.most_divisive,
      `Ranked #${w.teams[n.most_divisive].high} to #${w.teams[n.most_divisive].low} across outlets`));
  } else if (!used.has(bottom[0])) {
    tiles.push(tile('No. 32 overall', bottom[0], `Score ${bottom[1].avg} &middot; ${bottom[1].record}`));
  }
  $('tiles').textContent = '';
  tiles.filter(Boolean).slice(0, 4).forEach(t => $('tiles').appendChild(t));

  /* table */
  const cols = st.cols ? w.sources.map(s => s.id) : [];
  $('head').innerHTML = `<th class="l" style="width:32px">#</th><th style="width:50px">Move</th>
    <th class="l">Team</th><th>Rec</th>
    <th title="Average of every outlet's rank — lower is better">Score</th>
    <th title="Best and worst rank any single outlet gave">High/Low</th>
    <th class="l" title="Gap between the highest and lowest rank">Spread</th>` +
    cols.map(id => `<th class="num" title="${data.sourcesBy[id]?.name || id}">${shortName(data.sourcesBy[id]?.name || id)}</th>`).join('');

  const maxSpread = Math.max(1, ...Object.values(w.teams).map(t => t.spread));
  const frag = document.createDocumentFragment();
  for (const [abbr, t] of byRank) {
    if (st.filter && data.teamsBy[abbr].conference !== st.filter) continue;
    const tr = document.createElement('tr');
    const td = (html, cls = '') => { const c = document.createElement('td'); c.className = cls; c.innerHTML = html; return c; };
    tr.appendChild(td(String(t.rank), 'l rk'));
    const mv = td('', ''); mv.appendChild(movement(t.delta)); tr.appendChild(mv);
    const tc = td('', 'l'); tc.appendChild(teamLink(data.teamsBy[abbr])); tr.appendChild(tc);
    tr.appendChild(td(t.record, 'num'));
    tr.appendChild(td(t.avg.toFixed(2), 'score'));
    tr.appendChild(td(`${t.high}–${t.low}`, 'num'));
    tr.appendChild(td(`<span class="spread"><span class="meter"><i style="width:${
      Math.round(t.spread / maxSpread * 100)}%"></i></span><span class="num">${t.spread}</span></span>`, 'l'));
    for (const id of cols) {
      const r = t.ranks[id], dl = t.source_delta?.[id];
      tr.appendChild(td(r == null ? '<span style="color:var(--muted)">–</span>' :
        `${r}${dl ? ` <span style="font-size:10px;color:var(--${dl > 0 ? 'up' : 'down'})">${
          dl > 0 ? '▲' : '▼'}${Math.abs(dl)}</span>` : ''}`, 'num'));
    }
    frag.appendChild(tr);
  }
  $('rows').textContent = '';
  $('rows').appendChild(frag);

  $('srcList').innerHTML =
    w.sources.map(s => `<li><b>${s.name}</b>
      <span>${s.author ? s.author + ' · ' : ''}${fmtDate(s.published) || 'date n/a'}</span><br>
      <a href="${s.url}" target="_blank" rel="noopener">${(s.title || 'Read the article').slice(0,70)}</a></li>`).join('') +
    (w.failed_sources || []).map(f => `<li class="miss"><b>${f.name}</b>
      <span> not included this week</span><br>
      <span style="font-size:11.5px">${f.error}</span></li>`).join('');
}

/* ---- team view ---- */
const entry = (w, abbr) => w.teams[abbr];

function renderTeam() {
  const data = d(), abbr = st.abbr, team = data.teamsBy[abbr], w = wk(), t = entry(w, abbr);
  $('teamPick').value = abbr;
  $('hero').style.background =
    `linear-gradient(100deg, ${team.primary} 0%, ${team.primary} 58%, ${team.secondary} 190%)`;
  $('heroChip').textContent = team.abbr;
  $('heroName').textContent = team.name;
  $('heroSub').textContent = `${team.division} · ` +
    (w.games_through ? `${t.record} through Week ${w.games_through}` : 'preseason') +
    ` · ${data.season} ${w.label}`;
  const all = data.weeks.map(x => entry(x, abbr)?.rank).filter(Boolean);
  $('heroStats').innerHTML = `
    <div><b>#${t.rank}</b><span>Superpower</span></div>
    <div><b>${t.avg.toFixed(2)}</b><span>Score</span></div>
    <div><b>${t.high}–${t.low}</b><span>Outlet high/low</span></div>
    <div><b>${Math.min(...all)}</b><span>Season best</span></div>`;

  if (!st.legendFor || st.legendFor !== st.season) {
    st.legendFor = st.season;
    st.show = new Set(['consensus']);
    $('legend').textContent = '';
    $('legend').appendChild(legendBtn('consensus', 'Superpower', 'var(--ink)', true));
    data.sources.forEach((s, i) => $('legend').appendChild(
      legendBtn(s.id, s.name, OUTLET_COLORS[i % OUTLET_COLORS.length], false)));
  }

  $('outletTitle').textContent = `Outlet by outlet — ${w.label}`;
  $('outlets').textContent = '';
  for (const s of w.sources) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="l">${s.name}</td><td class="score">${t.ranks[s.id] ?? '–'}</td><td></td>
      <td class="l"><a href="${s.url}" target="_blank" rel="noopener"
        style="text-decoration:underline;text-underline-offset:2px">Article ↗</a></td>`;
    tr.children[2].appendChild(movement(t.source_delta?.[s.id] ?? null, '—'));
    $('outlets').appendChild(tr);
  }

  renderGames(data, abbr);
  renderWbw(data, abbr);
  drawChart();
}

function legendBtn(id, label, color, on) {
  const b = document.createElement('button');
  b.type = 'button';
  b.setAttribute('aria-pressed', String(on));
  b.innerHTML = `<span class="sw" style="background:${color}"></span>${label}`;
  b.onclick = () => {
    const now = b.getAttribute('aria-pressed') === 'true';
    b.setAttribute('aria-pressed', String(!now));
    now ? st.show.delete(id) : st.show.add(id);
    drawChart();
  };
  return b;
}

function withByes(log) {
  const reg = log.filter(g => g.season_type === 'regular');
  const post = log.filter(g => g.season_type !== 'regular');
  if (!reg.length) return log;
  const last = Math.max(...reg.map(g => g.week));
  const have = new Set(reg.map(g => g.week));
  const out = [];
  for (let i = 1; i <= last; i++) {
    out.push(have.has(i) ? reg.find(g => g.week === i)
      : { bye: true, week: i, label: `Week ${i}`, season_type: 'regular' });
  }
  return out.concat(post);
}

function renderGames(data, abbr) {
  const log = withByes(data.games[abbr] || []);
  let W = 0, L = 0, T = 0;
  for (const g of log) {
    if (g.bye || g.season_type !== 'regular' || !g.completed) continue;
    if (g.result === 'W') W++; else if (g.result === 'L') L++; else if (g.result === 'T') T++;
  }
  $('recordPill').textContent = `Season ${W}-${L}${T ? '-' + T : ''}`;
  $('games').textContent = '';
  if (!log.length) {
    $('games').innerHTML = '<tr><td class="empty" colspan="6">No games played yet.</td></tr>';
    return;
  }
  for (const g of log) {
    const tr = document.createElement('tr');
    if (g.bye) {
      tr.innerHTML = `<td class="l">${g.label}</td>
        <td class="l" style="color:var(--muted)">Bye week</td><td colspan="4"></td>`;
      $('games').appendChild(tr); continue;
    }
    const opp = data.teamsBy[g.opponent];
    const margin = g.points_for != null && g.points_against != null ? g.points_for - g.points_against : null;
    // Rankings after week W carry the label W+1. Playoff rounds reuse weeks 1-5,
    // so they must never be mapped onto a regular-season ranking week.
    const after = g.season_type === 'regular'
      ? (data.weeksBy[g.week + 1] && entry(data.weeksBy[g.week + 1], abbr)) || null : null;
    tr.innerHTML = `<td class="l">${g.label}</td><td class="l"></td>
      <td>${g.result ? `<span class="res ${g.result}">${g.result}</span>` : '<span style="color:var(--muted)">–</span>'}</td>
      <td class="num">${g.points_for != null ? `${g.points_for}–${g.points_against}`
        : `<span style="color:var(--muted)">${g.detail || 'TBD'}</span>`}</td>
      <td class="num">${margin != null ? (margin > 0 ? '+' : '') + margin : ''}</td>
      <td class="l"></td>`;
    const oc = document.createElement('a');
    oc.className = 'team'; oc.href = '#';
    oc.onclick = e => { e.preventDefault(); go('team', g.opponent); };
    oc.appendChild(chip(opp, 20));
    oc.insertAdjacentHTML('beforeend', `<span>${g.home ? '' : '@ '}${opp.nickname}</span>`);
    tr.children[1].appendChild(oc);
    if (after) {
      const box = document.createElement('span');
      box.style.cssText = 'display:inline-flex;align-items:center;gap:6px';
      box.innerHTML = `<b class="num">#${after.rank}</b>`;
      box.appendChild(movement(after.delta));
      tr.lastElementChild.appendChild(box);
    } else {
      tr.lastElementChild.innerHTML = '<span style="color:var(--muted)">–</span>';
    }
    $('games').appendChild(tr);
  }
}

function renderWbw(data, abbr) {
  const ids = data.sources.map(s => s.id);
  $('wbwHead').innerHTML = `<th class="l">Week</th><th>Superpower</th><th>Move</th><th>Score</th>` +
    ids.map(id => `<th class="num">${shortName(data.sourcesBy[id].name)}</th>`).join('');
  $('wbw').textContent = '';
  for (const w of data.weeks.slice().sort((a,b)=>b.week-a.week)) {
    const t = entry(w, abbr);
    if (!t) continue;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="l">${w.label}</td><td class="rk">${t.rank}</td><td></td>
      <td class="score">${t.avg.toFixed(2)}</td>` +
      ids.map(id => `<td class="num">${t.ranks[id] ?? '–'}</td>`).join('');
    tr.children[2].appendChild(movement(t.delta));
    $('wbw').appendChild(tr);
  }
}

/* rank chart — y inverted so #1 is at the top */
function drawChart() {
  const host = $('chart'), data = d(), abbr = st.abbr;
  const xs = data.weeks.map(w => w.week).sort((a,b)=>a-b);
  const series = [];
  data.sources.forEach((s, i) => {
    if (!st.show.has(s.id)) return;
    series.push({ label: s.name, color: OUTLET_COLORS[i % OUTLET_COLORS.length],
      width: 1.6, opacity: .85, dash: '4 3',
      points: xs.map(x => ({ x, y: entry(data.weeksBy[x], abbr)?.ranks?.[s.id] ?? null })) });
  });
  if (st.show.has('consensus')) {
    series.push({ label: 'Superpower',
      color: getComputedStyle(document.body).getPropertyValue('--ink').trim() || '#111',
      width: 2.6, dots: true,
      points: xs.map(x => ({ x, y: entry(data.weeksBy[x], abbr)?.rank ?? null })) });
  }

  host.textContent = '';
  const NS = 'http://www.w3.org/2000/svg';
  const mk = (t, a = {}) => { const e = document.createElementNS(NS, t);
    for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const W = Math.max(host.clientWidth || 620, 300), H = 300;
  const m = { t: 12, r: 14, b: 26, l: 30 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const X = v => m.l + (xMax === xMin ? iw / 2 : (v - xMin) / (xMax - xMin) * iw);
  const Y = v => m.t + (v - 1) / 31 * ih;

  const svg = mk('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
    role: 'img', 'aria-label': 'Superpower rank by week' });
  for (const r of [1, 8, 16, 24, 32]) {
    svg.appendChild(mk('line', { class: 'grid', x1: m.l, x2: W - m.r, y1: Y(r), y2: Y(r) }));
    const tx = mk('text', { class: 'axis', x: m.l - 7, y: Y(r) + 3.5, 'text-anchor': 'end' });
    tx.textContent = r; svg.appendChild(tx);
  }
  for (const x of xs) {
    const tx = mk('text', { class: 'axis', x: X(x), y: H - 8, 'text-anchor': 'middle' });
    tx.textContent = x; svg.appendChild(tx);
  }
  for (const s of series) {
    const pts = s.points.filter(p => p.y != null);
    if (!pts.length) continue;
    svg.appendChild(mk('path', {
      d: pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' '),
      fill: 'none', stroke: s.color, 'stroke-width': s.width,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      'stroke-opacity': s.opacity ?? 1, ...(s.dash ? { 'stroke-dasharray': s.dash } : {}) }));
    if (s.dots) for (const p of pts) {
      const c = mk('circle', { cx: X(p.x), cy: Y(p.y), r: 3.4, fill: s.color,
        stroke: 'var(--card)', 'stroke-width': 1.5 });
      const ti = mk('title'); ti.textContent = `${s.label} — Week ${p.x}: #${p.y}`;
      c.appendChild(ti); svg.appendChild(c);
    }
  }
  host.appendChild(svg);
}

st.week = Math.max(...d().weeks.map(w => w.week));
fillWeeks();
render();
