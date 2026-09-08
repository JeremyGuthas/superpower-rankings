/* Superpower Rankings — offline snapshot.
 *
 * The hosted site is four pages sharing a module; a snapshot has to be one
 * file, so the same four screens live here as views over embedded data.
 */

const D = window.__SPR__;
const $ = id => document.getElementById(id);

const S = {};
for (const [yr, data] of Object.entries(D.seasons)) {
  data.teamsBy = Object.fromEntries(data.teams.map(t => [t.abbr, t]));
  data.sourcesBy = Object.fromEntries(data.sources.map(s => [s.id, s]));
  data.weeksBy = Object.fromEntries(data.weeks.map(w => [w.week, w]));
  S[yr] = data;
}

const st = {
  season: String(D.default_season), view: 'board', week: null,
  abbr: 'LAR', cmpA: null, cmpB: null,
  group: 'outlets', filter: '', show: new Set(['consensus']),
  accHidden: new Set(), legendFor: null,
};

const d = () => S[st.season];
const wk = () => d().weeksBy[st.week];
const entry = (w, abbr) => w.teams[abbr];
const latest = data => Math.max(...data.weeks.map(w => w.week));

const OUTLET_COLORS = ['#c9762f', '#3f7cac', '#7a5195', '#2f8b6c', '#b23a6b',
  '#8a8730', '#0f6f8f', '#a3492a'];
const shortName = n => n.replace('Sharp Football Analysis', 'Sharp')
  .replace('Bleacher Report', 'B/R').replace(' Sports', '');
const signed = n => (n > 0 ? `+${n}` : String(n));
const fmtDate = iso => {
  if (!iso) return '';
  const x = new Date(iso);
  return isNaN(x) ? '' : x.toLocaleDateString('en-US',
    { month: 'short', day: 'numeric', year: 'numeric' });
};
const ordinalish = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10]
  || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');

/* ---------- colour contrast ----------
 * Team colours are brand values, not UI tokens: Rams navy on a dark ground and
 * Steelers gold under white text both fail. These pick a readable variant
 * without changing which colour the team is.
 */

const _rgb = hex => {
  const h = hex.replace('#', '');
  const n = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  return [0, 2, 4].map(i => parseInt(n.slice(i, i + 2), 16));
};

const _lin = c => {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
};

/** WCAG relative luminance, 0 (black) to 1 (white). */
const luminance = hex => {
  const [r, g, b] = _rgb(hex);
  return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b);
};

const _mix = (hex, towards, amount) => {
  const a = _rgb(hex), b = _rgb(towards);
  const out = a.map((v, i) => Math.round(v + (b[i] - v) * amount));
  return '#' + out.map(v => v.toString(16).padStart(2, '0')).join('');
};

const isDarkTheme = () => {
  const set = document.documentElement.dataset.theme;
  if (set) return set === 'dark';
  return matchMedia('(prefers-color-scheme: dark)').matches;
};

/** Nudge a team colour until it reads against the current page background. */
function readable(hex) {
  if (!hex) return 'currentColor';
  const l = luminance(hex);
  if (isDarkTheme()) return l < 0.22 ? _mix(hex, '#ffffff', 0.52) : hex;
  return l > 0.55 ? _mix(hex, '#000000', 0.38) : hex;
}

/** Black or white, whichever is legible on top of `hex`. */
const onColor = hex => (luminance(hex) > 0.42 ? '#101820' : '#ffffff');

/* ---------------- shared pieces ---------------- */

function chip(team, size) {
  const el = document.createElement('span');
  el.className = 'chip';
  el.style.background = team.primary;
  el.style.color = onColor(team.primary);
  el.style.boxShadow = `inset 0 0 0 1.5px ${team.secondary}`;
  el.textContent = team.abbr;
  if (size) el.style.width = el.style.height = el.style.flexBasis = size + 'px';
  const img = new Image();
  img.alt = ''; img.loading = 'lazy';
  img.src = `https://a.espncdn.com/i/teamlogos/nfl/500/${team.abbr.toLowerCase()}.png`;
  img.onerror = () => img.remove();     // falls back to the colour chip
  el.appendChild(img);
  return el;
}

function teamLink(team, division = true) {
  const a = document.createElement('a');
  a.className = 'team'; a.href = '#';
  a.onclick = e => { e.preventDefault(); go('team', { abbr: team.abbr }); };
  a.appendChild(chip(team));
  const t = document.createElement('span');
  t.innerHTML = `<span class="nm">${team.name}</span>` +
    (division ? ` <span class="div">${team.division}</span>` : '');
  a.appendChild(t);
  return a;
}

function movement(v, newLabel = 'NEW') {
  const el = document.createElement('span');
  if (v === null || v === undefined) { el.className = 'mv new'; el.textContent = newLabel; }
  else if (v > 0) { el.className = 'mv up'; el.textContent = `▲ ${v}`; }
  else if (v < 0) { el.className = 'mv down'; el.textContent = `▼ ${-v}`; }
  else { el.className = 'mv flat'; el.textContent = '–'; }
  return el;
}

function gapChip(value, positive = 'up') {
  const el = document.createElement('span');
  if (value === null || value === undefined) { el.className = 'mv flat'; el.textContent = '–'; return el; }
  const good = value > 0 ? positive === 'up' : positive === 'down';
  el.className = value === 0 ? 'mv flat' : `mv ${good ? 'up' : 'down'}`;
  el.textContent = value === 0 ? '–' : signed(value);
  return el;
}

const cell = (html, cls = '') => {
  const td = document.createElement('td');
  td.className = cls;
  td.innerHTML = html;
  return td;
};

/* rank/line chart — invert:true puts rank 1 at the top */
function lineChart(host, series, { xs, yMin = 1, yMax = 32, height = 300,
                                   invert = true, ticks = null, label = null } = {}) {
  host.textContent = '';
  const NS = 'http://www.w3.org/2000/svg';
  const mk = (t, a = {}) => {
    const e = document.createElementNS(NS, t);
    for (const [k, v] of Object.entries(a)) e.setAttribute(k, v);
    return e;
  };
  const W = Math.max(host.clientWidth || 620, 300), H = height;
  const m = { t: 12, r: 14, b: 26, l: 32 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
  const all = xs && xs.length ? xs : [1];
  const xMin = Math.min(...all), xMax = Math.max(...all);
  const X = v => m.l + (xMax === xMin ? iw / 2 : (v - xMin) / (xMax - xMin) * iw);
  const span = (yMax - yMin) || 1;
  const Y = v => invert ? m.t + (v - yMin) / span * ih : m.t + ih - (v - yMin) / span * ih;

  const svg = mk('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
    role: 'img', 'aria-label': label || 'Rank by week' });
  for (const r of (ticks || [1, 8, 16, 24, 32].filter(v => v >= yMin && v <= yMax))) {
    svg.appendChild(mk('line', { class: 'grid', x1: m.l, x2: W - m.r, y1: Y(r), y2: Y(r) }));
    const t = mk('text', { class: 'axis', x: m.l - 7, y: Y(r) + 3.5, 'text-anchor': 'end' });
    t.textContent = r;
    svg.appendChild(t);
  }
  for (const x of all) {
    const t = mk('text', { class: 'axis', x: X(x), y: H - 8, 'text-anchor': 'middle' });
    t.textContent = x;
    svg.appendChild(t);
  }
  for (const s of series) {
    const pts = (s.points || []).filter(p => p.y != null);
    if (!pts.length) continue;
    svg.appendChild(mk('path', {
      d: pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' '),
      fill: 'none', stroke: s.color, 'stroke-width': s.width || 2,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      'stroke-opacity': s.opacity ?? 1, ...(s.dash ? { 'stroke-dasharray': s.dash } : {}) }));
    if (s.dots) for (const p of pts) {
      const c = mk('circle', { cx: X(p.x), cy: Y(p.y), r: 3.4, fill: s.color,
        stroke: 'var(--card)', 'stroke-width': 1.5 });
      const ti = mk('title');
      ti.textContent = `${s.label} — Week ${p.x}: ${invert ? '#' : ''}${p.y}`;
      c.appendChild(ti);
      svg.appendChild(c);
    }
  }
  host.appendChild(svg);
}

function legendButton(label, color, on, toggle) {
  const b = document.createElement('button');
  b.type = 'button';
  b.setAttribute('aria-pressed', String(on));
  b.innerHTML = `<span class="swatch" style="background:${color}"></span>${label}`;
  b.onclick = () => {
    const now = b.getAttribute('aria-pressed') === 'true';
    b.setAttribute('aria-pressed', String(!now));
    toggle(!now);
  };
  return b;
}

const inkColor = () =>
  getComputedStyle(document.body).getPropertyValue('--ink').trim() || '#111';

/* ---------------- chrome ---------------- */

try { const t = localStorage.getItem('spr-theme'); if (t) document.documentElement.dataset.theme = t; }
catch { /* private mode */ }

$('theme').onclick = () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  const next = dark ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('spr-theme', next); } catch { /* ignore */ }
  render();
};

for (const b of document.querySelectorAll('.navlink')) {
  b.onclick = () => go(b.dataset.view);
}
$('home').onclick = e => { e.preventDefault(); go('board'); };

$('season').innerHTML = Object.keys(S).sort((a, b) => b - a)
  .map(y => `<option value="${y}">${y} season</option>`).join('');
$('season').value = st.season;
$('season').onchange = e => {
  st.season = e.target.value;
  st.week = latest(d());
  st.legendFor = null;
  st.cmpA = st.cmpB = null;
  fillPickers();
  render();
};
$('week').onchange = e => { st.week = Number(e.target.value); render(); };
$('prev').onclick = () => step(-1);
$('next').onclick = () => step(1);
$('gOutlets').onclick = () => { st.group = st.group === 'outlets' ? 'none' : 'outlets'; render(); };
$('gContext').onclick = () => { st.group = st.group === 'context' ? 'none' : 'context'; render(); };
$('filter').onchange = e => { st.filter = e.target.value; render(); };
$('teamPick').onchange = e => {
  if (st.view === 'compare') st.cmpA = e.target.value; else st.abbr = e.target.value;
  render();
};
$('teamB').onchange = e => { st.cmpB = e.target.value; render(); };
$('swap').onclick = () => { [st.cmpA, st.cmpB] = [st.cmpB, st.cmpA]; render(); };
addEventListener('resize', () => render());

function fillPickers() {
  const data = d();
  $('week').innerHTML = data.weeks.slice().sort((a, b) => b.week - a.week)
    .map(w => `<option value="${w.week}">${w.label}</option>`).join('');
  $('week').value = st.week;
  const opts = data.teams.map(t => `<option value="${t.abbr}">${t.name}</option>`).join('');
  $('teamPick').innerHTML = opts;
  $('teamB').innerHTML = opts;
  $('divs').innerHTML = [...new Set(data.teams.map(t => t.division))].sort()
    .map(v => `<option value="div:${v}">${v}</option>`).join('');
}

function step(dir) {
  const ws = d().weeks.map(w => w.week).sort((a, b) => a - b);
  const i = ws.indexOf(st.week) + dir;
  if (i >= 0 && i < ws.length) { st.week = ws[i]; $('week').value = st.week; render(); }
}

function go(view, opts = {}) {
  st.view = view;
  if (opts.abbr) st.abbr = opts.abbr;
  scrollTo({ top: 0 });
  render();
}

/* ---------------- render ---------------- */

function render() {
  const data = d();
  const ws = data.weeks.map(w => w.week).sort((a, b) => a - b);
  if (!data.weeksBy[st.week]) st.week = ws[ws.length - 1];
  $('week').value = st.week;
  $('prev').disabled = st.week === ws[0];
  $('next').disabled = st.week === ws[ws.length - 1];

  const w = wk();
  const board = st.view === 'board', team = st.view === 'team';
  const compare = st.view === 'compare', acc = st.view === 'accuracy';

  for (const [id, on] of [['viewBoard', board], ['viewTeam', team],
    ['viewCompare', compare], ['viewAccuracy', acc], ['hero', team]]) {
    $(id).classList.toggle('hidden', !on);
  }
  for (const [id, on] of [['weekPick', !acc], ['groups', board], ['filter', board],
    ['teamPick', team || compare], ['teamB', compare], ['swap', compare]]) {
    $(id).classList.toggle('hidden', !on);
  }
  for (const b of document.querySelectorAll('.navlink')) {
    const current = b.dataset.view === st.view || (team && b.dataset.view === 'board');
    b.toggleAttribute('aria-current', current);
    if (current) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }

  $('meta').innerHTML = acc
    ? `${data.season} season &middot; ${data.weeks.length} week${data.weeks.length === 1 ? '' : 's'}`
    : `${w.sources.length} outlet${w.sources.length === 1 ? '' : 's'}` +
      ` &middot; ${w.games_through ? 'through Week ' + w.games_through : 'preseason'}`;
  $('snapshotStamp').textContent = `Data compiled ${fmtDate(data.generated)}.`;
  $('snapnote').textContent =
    `Offline snapshot — the data is frozen as of ${fmtDate(data.generated)}. ` +
    `The hosted site refreshes itself every Tuesday.`;

  if (board) renderBoard();
  else if (team) renderTeam();
  else if (compare) renderCompare();
  else renderAccuracy();
}

/* ---- board ---- */

function renderBoard() {
  const data = d(), w = wk();
  $('boardTitle').textContent = `${data.season} ${w.label} Superpower Rankings`;
  $('srcCount').textContent = `${w.sources.length} outlet${w.sources.length === 1 ? '' : 's'}`;
  $('teamPick').value = st.abbr;

  const n = w.storylines || w.notes || {};
  const notes = w.notes || {};
  const byRank = Object.entries(w.teams).sort((a, b) => a[1].rank - b[1].rank);
  const top = byRank[0], bottom = byRank[byRank.length - 1];
  const used = new Set([top[0]]);
  if (notes.biggest_riser) used.add(notes.biggest_riser);
  if (notes.biggest_faller) used.add(notes.biggest_faller);
  const tightest = byRank.filter(([a]) => !used.has(a))
    .sort((a, b) => a[1].spread - b[1].spread)[0];
  const move = a => {
    const v = w.teams[a].delta;
    return v > 0 ? `up ${v}` : v < 0 ? `down ${-v}` : 'unchanged';
  };

  const tile = (title, abbr, sub) => {
    if (!abbr) return null;
    const t = data.teamsBy[abbr];
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `<h3>${title}</h3>`;
    const row = document.createElement('div');
    row.className = 'big';
    row.appendChild(chip(t, 22));
    const a = document.createElement('a');
    a.href = '#'; a.textContent = t.name;
    a.onclick = e => { e.preventDefault(); go('team', { abbr }); };
    row.appendChild(a);
    el.appendChild(row);
    el.insertAdjacentHTML('beforeend', `<div class="sub">${sub}</div>`);
    return el;
  };

  const tiles = [tile('No. 1 overall', top[0], `Score ${top[1].avg} &middot; ${top[1].record}`)];
  if (notes.biggest_riser && w.teams[notes.biggest_riser].delta > 0) {
    tiles.push(tile('Biggest riser', notes.biggest_riser,
      `${move(notes.biggest_riser)} to #${w.teams[notes.biggest_riser].rank}`));
    tiles.push(tile('Biggest faller', notes.biggest_faller,
      `${move(notes.biggest_faller)} to #${w.teams[notes.biggest_faller].rank}`));
  } else {
    tiles.push(tile('No. 32 overall', bottom[0], `Score ${bottom[1].avg}`));
    if (tightest) tiles.push(tile('Tightest consensus', tightest[0],
      `Every outlet within ${tightest[1].spread} spot${tightest[1].spread === 1 ? '' : 's'}`));
  }
  if (w.sources.length > 1 && notes.most_divisive) {
    tiles.push(tile('Most divisive', notes.most_divisive,
      `Ranked #${w.teams[notes.most_divisive].high} to #${w.teams[notes.most_divisive].low} across outlets`));
  } else if (!used.has(bottom[0])) {
    tiles.push(tile('No. 32 overall', bottom[0], `Score ${bottom[1].avg} &middot; ${bottom[1].record}`));
  }
  $('cards').textContent = '';
  tiles.filter(Boolean).slice(0, 4).forEach(t => $('cards').appendChild(t));

  renderStories(w, data, n);
  renderBoardTable(w, data, byRank);
  renderSources(w);
}

function renderStories(w, data, s) {
  const link = a => {
    const t = data.teamsBy[a];
    return `<a href="#" data-team="${a}"><b>${t.name}</b></a>`;
  };
  const fill = (id, items, make, empty) => {
    const host = $(id);
    host.innerHTML = (!items || !items.length)
      ? `<li class="none">${empty}</li>`
      : items.slice(0, 4).map(i => `<li>${make(i)}</li>`).join('');
    for (const a of host.querySelectorAll('a[data-team]')) {
      a.onclick = e => { e.preventDefault(); go('team', { abbr: a.dataset.team }); };
    }
  };

  fill('laneOutliers', s.outliers, o => {
    const outlet = data.sourcesBy[o.source]?.name || o.source;
    const side = o.gap > 0 ? 'higher' : 'lower';
    return `${link(o.team)} at <b>#${o.rank}</b> on ${outlet}
      <span class="why">${Math.abs(o.gap)} spots ${side} than the consensus #${o.consensus}</span>`;
  }, w.sources.length < 3
      ? 'At least three outlets are needed before one can be called an outlier.'
      : 'Every outlet is within a few spots of the consensus this week.');

  fill('laneDiverge', s.divergent, v => {
    const side = v.gap > 0 ? 'ahead of' : 'behind';
    return `${link(v.team)} <span class="flag ${v.gap > 0 ? 'hot' : 'cold'}">${signed(v.gap)}</span>
      <span class="why">#${v.rank} in the rankings, #${v.record_rank} on results (${v.record})
      — rated ${Math.abs(v.gap)} spots ${side} what they have earned</span>`;
  }, w.games_through
      ? 'No team is far from where its record puts it.'
      : 'No games played yet — this comparison starts once Week 1 is in the books.');

  const meta = s.market_meta;
  $('marketHead').textContent = meta?.provider
    ? `Media vs. the market (${meta.provider})` : 'Media vs. the market';
  fill('laneMarket', s.market, m => {
    const believer = m.gap > 0 ? 'the market' : 'the media';
    return `${link(m.team)} <span class="od">${m.odds}</span>
      <span class="why">#${m.rank} in the consensus, #${m.market_rank} at the book
      — ${believer} is the believer by ${Math.abs(m.gap)} spots</span>`;
  }, meta ? 'The board and the betting market broadly agree.'
          : 'Betting odds are not available for this week.');
}

function renderBoardTable(w, data, byRank) {
  const outlets = st.group === 'outlets' ? w.sources.map(s => s.id) : [];
  const context = st.group === 'context';
  $('gOutlets').setAttribute('aria-pressed', String(st.group === 'outlets'));
  $('gContext').setAttribute('aria-pressed', String(context));
  const hasMarket = Object.values(w.teams).some(t => t.market_rank);

  $('head').innerHTML = `
    <th class="l" style="width:34px">#</th><th style="width:52px">Move</th>
    <th class="l">Team</th><th>Rec</th>
    <th title="Average of every outlet's rank — lower is better">Score</th>
    <th title="Best and worst rank any single outlet gave">High/Low</th>
    <th class="l" title="Gap between the highest and lowest rank">Spread</th>
    ${outlets.map(id => `<th class="src" title="${data.sourcesBy[id]?.name || id}">${
      shortName(data.sourcesBy[id]?.name || id)}</th>`).join('')}
    ${context ? `
      <th class="l" title="The next opponent, with their Superpower rank">Next up</th>
      <th title="Average Superpower rank of the remaining opponents — lower is tougher">Rest SOS</th>
      <th title="Where results alone would rank this team">By record</th>
      <th title="Ranking minus record rank">Gap</th>
      ${hasMarket ? `<th title="Rank implied by Super Bowl odds">Market</th>
        <th title="Superpower rank minus market rank">Edge</th>` : ''}` : ''}`;

  const maxSpread = Math.max(1, ...Object.values(w.teams).map(t => t.spread));
  const frag = document.createDocumentFragment();
  for (const [abbr, t] of byRank) {
    const team = data.teamsBy[abbr];
    if (st.filter) {
      const ok = st.filter.startsWith('div:')
        ? team.division === st.filter.slice(4) : team.conference === st.filter;
      if (!ok) continue;
    }
    const tr = document.createElement('tr');
    tr.appendChild(cell(String(t.rank), 'l rk'));
    const mv = cell('', ''); mv.appendChild(movement(t.delta)); tr.appendChild(mv);
    const tc = cell('', 'l'); tc.appendChild(teamLink(team)); tr.appendChild(tc);
    tr.appendChild(cell(t.record, 'num'));
    tr.appendChild(cell(t.avg.toFixed(2), 'score'));
    tr.appendChild(cell(`${t.high}–${t.low}`, 'num'));
    tr.appendChild(cell(`<span class="spread"><span class="meter"><i style="width:${
      Math.round(t.spread / maxSpread * 100)}%"></i></span><span class="num">${t.spread}</span></span>`, 'l'));

    for (const id of outlets) {
      const r = t.ranks[id], dl = t.source_delta?.[id];
      tr.appendChild(cell(r == null ? '<span style="color:var(--muted)">–</span>' :
        `${r}${dl ? ` <span style="font-size:10px;color:var(--${dl > 0 ? 'up' : 'down'})">${
          dl > 0 ? '▲' : '▼'}${Math.abs(dl)}</span>` : ''}`, 'num'));
    }

    if (context) {
      const ng = t.next_game;
      if (ng) {
        const opp = data.teamsBy[ng.opponent];
        const td = cell(`${ng.home ? 'vs' : '@'} <a href="#" data-team="${ng.opponent}"><b>${
          opp.abbr}</b></a>` + (ng.opponent_rank ? ` <span class="flag">#${ng.opponent_rank}</span>` : ''), 'l');
        td.querySelector('a').onclick = e => {
          e.preventDefault(); go('team', { abbr: ng.opponent });
        };
        tr.appendChild(td);
      } else {
        tr.appendChild(cell('<span style="color:var(--muted)">season over</span>', 'l'));
      }
      tr.appendChild(cell(t.sos_remaining != null ? t.sos_remaining.toFixed(1) : '–', 'num'));
      tr.appendChild(cell(t.record_rank ?? '–', 'num'));
      const dv = cell('', ''); dv.appendChild(gapChip(t.divergence ?? null)); tr.appendChild(dv);
      if (hasMarket) {
        tr.appendChild(cell(t.market_rank ?? '–', 'num'));
        const mk = cell('', '');
        mk.appendChild(gapChip(t.market_gap ?? null));
        if (t.market_odds) mk.title = `Super Bowl odds ${t.market_odds}`;
        tr.appendChild(mk);
      }
    }
    frag.appendChild(tr);
  }
  $('rows').textContent = '';
  $('rows').appendChild(frag);
}

function renderSources(w) {
  $('srcList').innerHTML =
    w.sources.map(s => `<li><b>${s.name}</b>
      <span>${s.author ? s.author + ' · ' : ''}${fmtDate(s.published) || 'date n/a'}</span><br>
      <a href="${s.url}" target="_blank" rel="noopener">${(s.title || 'Read the article').slice(0, 70)}</a></li>`).join('') +
    (w.failed_sources || []).map(f => `<li class="warn"><b>${f.name}</b>
      <span> not included this week</span><br>
      <span style="font-size:11.5px">${f.error}</span></li>`).join('');
}

/* ---- team ---- */

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

  renderContext(w, t, data, team);

  $('outletTitle').textContent = `Outlet by outlet — ${w.label}`;
  $('outlets').textContent = '';
  for (const s of w.sources) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="l">${s.name}</td><td class="score">${t.ranks[s.id] ?? '–'}</td>
      <td></td><td class="l"><a href="${s.url}" target="_blank" rel="noopener"
      style="text-decoration:underline;text-underline-offset:2px">Article ↗</a></td>`;
    tr.children[2].appendChild(movement(t.source_delta?.[s.id] ?? null, '—'));
    $('outlets').appendChild(tr);
  }

  if (st.legendFor !== st.season) {
    st.legendFor = st.season;
    st.show = new Set(['consensus']);
    $('legend').textContent = '';
    $('legend').appendChild(legendButton('Superpower', inkColor(), true,
      on => { on ? st.show.add('consensus') : st.show.delete('consensus'); drawTeamChart(); }));
    data.sources.forEach((s, i) => $('legend').appendChild(
      legendButton(s.name, OUTLET_COLORS[i % OUTLET_COLORS.length], false,
        on => { on ? st.show.add(s.id) : st.show.delete(s.id); drawTeamChart(); })));
  }

  renderGames(data, abbr);
  renderWbw(data, abbr);
  drawTeamChart();
}

function renderContext(w, t, data, team) {
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
    const opp = data.teamsBy[ng.opponent];
    const row = document.createElement('span');
    row.style.cssText = 'display:inline-flex;align-items:center;gap:8px';
    row.insertAdjacentHTML('beforeend',
      `<span style="color:var(--muted);font-weight:600">${ng.home ? 'vs' : '@'}</span>`);
    row.appendChild(chip(opp, 22));
    const a = document.createElement('a');
    a.href = '#'; a.textContent = opp.nickname;
    a.onclick = e => { e.preventDefault(); go('team', { abbr: ng.opponent }); };
    row.appendChild(a);
    cards.push(card('Next up', row,
      `${ng.label}${ng.opponent_rank ? ` &middot; opponent ranked #${ng.opponent_rank}` : ''}`));
  } else {
    cards.push(card('Next up', '<span style="color:var(--muted)">Season complete</span>',
      'No fixtures remaining'));
  }

  cards.push(card('Remaining schedule',
    t.sos_remaining != null ? `<span class="score">${t.sos_remaining.toFixed(1)}</span>`
      : '<span style="color:var(--muted)">–</span>',
    t.sos_rank ? `${ordinalish(t.sos_rank)} toughest of 32 &middot; ${t.opponents_remaining} to play`
      : 'Average Superpower rank of remaining opponents'));

  const rec = document.createElement('span');
  rec.style.cssText = 'display:inline-flex;align-items:center;gap:8px';
  rec.innerHTML = t.record_rank ? `<span class="score">#${t.record_rank}</span>`
    : '<span style="color:var(--muted)">–</span>';
  if (t.divergence != null) rec.appendChild(gapChip(t.divergence));
  cards.push(card('By record alone', rec,
    t.divergence == null ? 'Available once games are played'
      : t.divergence > 0 ? `Ranked ${Math.abs(t.divergence)} spots better than results justify`
      : t.divergence < 0 ? `Ranked ${Math.abs(t.divergence)} spots below what results justify`
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
  note.classList.toggle('hidden', !o);
  if (o) {
    const outlet = data.sourcesBy[o.source]?.name || o.source;
    note.innerHTML = `<b>${outlet} is the outlier on ${team.name}.</b> They have them at
      <b>#${o.rank}</b> — ${Math.abs(o.gap)} spots ${o.gap > 0 ? 'higher' : 'lower'} than the
      consensus at #${t.rank}, the widest gap any single outlet has on this team.`;
  }
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
      $('games').appendChild(tr);
      continue;
    }
    const opp = data.teamsBy[g.opponent];
    const margin = g.points_for != null && g.points_against != null
      ? g.points_for - g.points_against : null;
    // Rankings after week W carry the label W+1; playoff rounds reuse weeks
    // 1-5, so they must never be mapped onto a regular-season ranking week.
    const after = g.season_type === 'regular'
      ? (data.weeksBy[g.week + 1] && entry(data.weeksBy[g.week + 1], abbr)) || null : null;
    tr.innerHTML = `<td class="l">${g.label}</td><td class="l"></td>
      <td>${g.result ? `<span class="res ${g.result}">${g.result}</span>`
        : '<span style="color:var(--muted)">–</span>'}</td>
      <td class="num">${g.points_for != null ? `${g.points_for}–${g.points_against}`
        : `<span style="color:var(--muted)">${g.detail || 'TBD'}</span>`}</td>
      <td class="num">${margin != null ? (margin > 0 ? '+' : '') + margin : ''}</td>
      <td class="l"></td>`;
    const oc = document.createElement('a');
    oc.className = 'team'; oc.href = '#';
    oc.onclick = e => { e.preventDefault(); go('team', { abbr: g.opponent }); };
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
    ids.map(id => `<th class="src">${shortName(data.sourcesBy[id].name)}</th>`).join('');
  $('wbw').textContent = '';
  for (const w of data.weeks.slice().sort((a, b) => b.week - a.week)) {
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

function drawTeamChart() {
  const data = d(), abbr = st.abbr;
  const xs = data.weeks.map(w => w.week).sort((a, b) => a - b);
  const series = [];
  data.sources.forEach((s, i) => {
    if (!st.show.has(s.id)) return;
    series.push({ label: s.name, color: OUTLET_COLORS[i % OUTLET_COLORS.length],
      width: 1.6, opacity: .85, dash: '4 3',
      points: xs.map(x => ({ x, y: entry(data.weeksBy[x], abbr)?.ranks?.[s.id] ?? null })) });
  });
  if (st.show.has('consensus')) {
    series.push({ label: 'Superpower', color: inkColor(), width: 2.6, dots: true,
      points: xs.map(x => ({ x, y: entry(data.weeksBy[x], abbr)?.rank ?? null })) });
  }
  lineChart($('chart'), series, { xs });
}

/* ---- compare ---- */

function renderCompare() {
  const data = d(), w = wk();
  const byRank = Object.entries(w.teams).sort((a, b) => a[1].rank - b[1].rank);
  if (!st.cmpA || !data.teamsBy[st.cmpA]) st.cmpA = st.abbr || byRank[0][0];
  if (!st.cmpB || !data.teamsBy[st.cmpB] || st.cmpB === st.cmpA) {
    st.cmpB = byRank.find(([a]) => a !== st.cmpA)[0];
  }
  $('teamPick').value = st.cmpA;
  $('teamB').value = st.cmpB;
  $('cmpTitle').textContent =
    `${data.teamsBy[st.cmpA].nickname} vs ${data.teamsBy[st.cmpB].nickname} — ${w.label}`;

  compareSide('sideA', st.cmpA);
  compareSide('sideB', st.cmpB);
  compareRows(w, data);
  compareH2H(data);

  const xs = data.weeks.map(x => x.week).sort((a, b) => a - b);
  lineChart($('cmpChart'), [st.cmpA, st.cmpB].map(abbr => ({
    label: data.teamsBy[abbr].nickname, color: readable(data.teamsBy[abbr].primary),
    width: 2.6, dots: true,
    points: xs.map(x => ({ x, y: data.weeksBy[x].teams[abbr]?.rank ?? null })),
  })), { xs });
}

function compareSide(id, abbr) {
  const data = d(), t = data.teamsBy[abbr], e = wk().teams[abbr];
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

function compareRows(w, data) {
  const A = w.teams[st.cmpA], B = w.teams[st.cmpB];
  const lower = (x, y) => (x == null || y == null) ? 0 : (x < y ? -1 : x > y ? 1 : 0);
  const higher = (x, y) => -lower(x, y);

  const rows = [
    ['Superpower rank', A.rank, B.rank, lower(A.rank, B.rank), v => `#${v}`],
    ['Score (avg rank)', A.avg, B.avg, lower(A.avg, B.avg), v => v.toFixed(2)],
    ['Record', A.record, B.record, 0, v => v],
    ['Rank by record', A.record_rank, B.record_rank, lower(A.record_rank, B.record_rank),
      v => v ? `#${v}` : '–'],
    ['Point differential', A.differential, B.differential,
      higher(A.differential, B.differential), v => (v > 0 ? '+' : '') + v],
    ['Best outlet rank', A.high, B.high, lower(A.high, B.high), v => `#${v}`],
    ['Worst outlet rank', A.low, B.low, lower(A.low, B.low), v => `#${v}`],
    ['Outlet spread', A.spread, B.spread, lower(A.spread, B.spread), v => `${v} spots`],
    ['Remaining SOS', A.sos_remaining, B.sos_remaining,
      lower(A.sos_remaining, B.sos_remaining), v => v != null ? v.toFixed(1) : '–'],
  ];
  if (A.market_rank || B.market_rank) {
    rows.push(['Market rank', A.market_rank, B.market_rank,
      lower(A.market_rank, B.market_rank), v => v ? `#${v}` : '–']);
    rows.push(['Super Bowl odds', A.market_odds, B.market_odds, 0, v => v || '–']);
  }
  for (const s of w.sources) {
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
    if (better < 0) tr.children[0].style.color = readable(data.teamsBy[st.cmpA].primary);
    if (better > 0) tr.children[2].style.color = readable(data.teamsBy[st.cmpB].primary);
    frag.appendChild(tr);
  }
  $('cmp').textContent = '';
  $('cmp').appendChild(frag);
}

function compareH2H(data) {
  const meetings = (data.games[st.cmpA] || []).filter(g => g.opponent === st.cmpB);
  if (!meetings.length) {
    $('h2h').innerHTML =
      `<tr><td class="empty" colspan="4">These two don't meet this season.</td></tr>`;
    return;
  }
  $('h2h').innerHTML = meetings.map(g => {
    const home = g.home ? st.cmpA : st.cmpB, away = g.home ? st.cmpB : st.cmpA;
    const played = g.completed && g.points_for != null;
    const score = played
      ? (g.home ? `${g.points_for}–${g.points_against}` : `${g.points_against}–${g.points_for}`)
      : `<span style="color:var(--muted)">${g.detail || 'not played yet'}</span>`;
    const res = played ? `<span class="res ${g.result}">${st.cmpA} ${g.result}</span>`
      : '<span style="color:var(--muted)">–</span>';
    return `<tr><td class="l">${g.label}</td>
      <td class="l">${data.teamsBy[away].nickname} at ${data.teamsBy[home].nickname}</td>
      <td>${res}</td><td class="num">${score}</td></tr>`;
  }).join('');
}

/* ---- accuracy ---- */

function renderAccuracy() {
  const data = d(), a = data.accuracy || {};
  if (!a.available) {
    $('verdict').innerHTML = `<b>Nothing to score yet.</b> ${
      a.reason || 'Outlets can only be graded once games have been played.'} ` +
      `Every ranking published in the meantime is stored and will be scored retroactively.`;
    $('accRows').innerHTML = '<tr><td class="empty" colspan="8">No completed games yet.</td></tr>';
    $('accLegend').textContent = '';
    $('accChart').textContent = '';
    return;
  }

  const c = a.consensus, sum = a.summary;
  const nameOf = id => (a.sources.find(r => r.id === id) || {}).name || id;
  if (sum && sum.outlets_scored < 2) {
    $('verdict').innerHTML = `<b>Only one outlet is scored for this season</b>, so the consensus
      is that outlet — averaging has nothing to average yet. It came in <b>${c.mae}</b> places
      off on the typical team.`;
  } else if (sum) {
    const beaten = sum.outlets_that_beat_it.length;
    $('verdict').innerHTML = beaten === 0
      ? `<b>The average beat every outlet that fed it.</b> The Superpower consensus finished
         <b>${c.mae}</b> places off on the typical team — closer than all ${sum.outlets_scored}
         outlets scored. This is the case for aggregating in one line.`
      : `<b>${beaten} of ${sum.outlets_scored} outlets beat the average.</b> The consensus
         finished <b>${c.mae}</b> places off on the typical team; ${
          sum.outlets_that_beat_it.map(nameOf).map(n => `<b>${n}</b>`).join(', ')} did better.`;
  }

  const worst = Math.max(...a.sources.map(r => r.mae), c?.mae ?? 0) || 1;
  const line = (r, isConsensus) => {
    const tr = document.createElement('tr');
    if (isConsensus) tr.className = 'consensus';
    tr.innerHTML = `
      <td class="l rk">${isConsensus ? '★' : r.place}</td>
      <td class="l">${r.name}</td>
      <td class="num">${r.weeks}</td>
      <td class="l"><span class="scorebar"><span class="track"><i style="width:${
        Math.round(r.mae / worst * 100)}%"></i></span><span class="num">${r.mae.toFixed(2)}</span></span></td>
      <td class="num">${r.spearman.toFixed(3)}</td>
      <td class="num">${r.early_mae != null ? r.early_mae.toFixed(2) : '–'}</td>
      <td class="num">Wk ${r.best_week.week} <span style="color:var(--muted)">${r.best_week.mae.toFixed(1)}</span></td>
      <td class="num">Wk ${r.worst_week.week} <span style="color:var(--muted)">${r.worst_week.mae.toFixed(1)}</span></td>`;
    return tr;
  };
  $('accRows').textContent = '';
  if (c) $('accRows').appendChild(line(c, true));
  a.sources.forEach(r => $('accRows').appendChild(line(r, false)));

  $('accLegend').textContent = '';
  const entries = [['consensus', 'Superpower consensus', inkColor()],
    ...a.sources.map((r, i) => [r.id, r.name, OUTLET_COLORS[i % OUTLET_COLORS.length]])];
  for (const [id, label, color] of entries) {
    $('accLegend').appendChild(legendButton(label, color, !st.accHidden.has(id), on => {
      on ? st.accHidden.delete(id) : st.accHidden.add(id);
      drawAccuracyChart();
    }));
  }
  drawAccuracyChart();
}

function drawAccuracyChart() {
  const a = d().accuracy || {};
  if (!a.available) return;
  const all = [a.consensus, ...a.sources].filter(Boolean);
  const xs = [...new Set(all.flatMap(r => r.by_week.map(p => p.week)))].sort((x, y) => x - y);
  const peak = Math.max(...all.flatMap(r => r.by_week.map(p => p.mae ?? 0)));
  const top = Math.max(2, Math.ceil(peak));
  const step = top <= 6 ? 1 : Math.ceil(top / 5);
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);

  const series = all.filter(r => !st.accHidden.has(r.id)).map(r => ({
    label: r.name,
    color: r.id === 'consensus' ? inkColor()
      : OUTLET_COLORS[a.sources.findIndex(s => s.id === r.id) % OUTLET_COLORS.length],
    width: r.id === 'consensus' ? 2.75 : 1.7,
    dash: r.id === 'consensus' ? null : '4 3',
    dots: r.id === 'consensus',
    points: r.by_week.filter(p => p.mae != null).map(p => ({ x: p.week, y: p.mae })),
  }));
  lineChart($('accChart'), series, {
    xs, yMin: 0, yMax: top, ticks, invert: false,
    label: 'Average ranking error by week, in places',
  });
}

/* ---------------- go ---------------- */

st.week = latest(d());
fillPickers();
render();
