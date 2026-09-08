import {
  loadIndex, loadSeason, latestWeek, teamCell, movement, chip, fmtDate, initTheme,
  shortName,
} from './app.js';

const $ = id => document.getElementById(id);
initTheme($('theme'));

const state = { data: null, week: null, cols: true, filter: '' };

boot().catch(err => {
  $('rows').innerHTML = `<tr><td class="empty" colspan="9">${err.message}</td></tr>`;
});

async function boot() {
  const url = new URL(location.href);
  const idx = await loadIndex();
  const seasons = idx.seasons.map(s => s.season);
  const asked = Number(url.searchParams.get('season'));
  const season = seasons.includes(asked) ? asked : idx.default_season;
  $('season').innerHTML = seasons
    .map(y => `<option value="${y}">${y} season</option>`).join('');
  $('season').value = season;
  $('season').onchange = e => {
    location.href = `index.html?season=${e.target.value}`;
  };

  const data = await loadSeason(season);
  state.data = data;
  if (!data.weeks.length) {
    $('rows').innerHTML = `<tr><td class="empty" colspan="9">
      No rankings stored yet. Run <code>python -m superpower.run</code> to build a week.</td></tr>`;
    return;
  }
  const askedWeek = Number(url.searchParams.get('week'));
  state.week = data.weeksBy[askedWeek] ? askedWeek : latestWeek(data);

  $('week').innerHTML = data.weeks
    .slice().sort((a, b) => b.week - a.week)
    .map(w => `<option value="${w.week}">${w.label}</option>`).join('');
  $('week').value = state.week;

  $('week').onchange = e => { state.week = Number(e.target.value); render(); };
  $('prev').onclick = () => step(-1);
  $('next').onclick = () => step(+1);
  $('cols').onchange = e => { state.cols = e.target.checked; render(); };
  $('filter').onchange = e => { state.filter = e.target.value; render(); };
  render();
}

function step(dir) {
  const weeks = state.data.weeks.map(w => w.week).sort((a, b) => a - b);
  const i = weeks.indexOf(state.week) + dir;
  if (i >= 0 && i < weeks.length) { state.week = weeks[i]; $('week').value = state.week; render(); }
}

function render() {
  const d = state.data;
  const wk = d.weeksBy[state.week];
  const weeks = d.weeks.map(w => w.week).sort((a, b) => a - b);
  $('prev').disabled = state.week === weeks[0];
  $('next').disabled = state.week === weeks[weeks.length - 1];
  history.replaceState(null, '', `?season=${d.season}&week=${state.week}`);

  const used = wk.sources.map(s => s.id);
  $('boardTitle').textContent = `${d.season} ${wk.label} Superpower Rankings`;
  $('srcCount').textContent = `${used.length} outlet${used.length === 1 ? '' : 's'}`;
  $('meta').innerHTML = `Updated ${fmtDate(wk.generated)}` +
    (wk.games_through ? ` &middot; through Week ${wk.games_through}` : ' &middot; preseason');
  $('stamp').textContent = `Data compiled ${fmtDate(d.generated)}.`;

  renderCards(wk, d);
  renderTable(wk, d, used);
  renderSources(wk);
}

function renderCards(wk, d) {
  const n = wk.notes || {};
  const byRank = Object.entries(wk.teams).sort((a, b) => a[1].rank - b[1].rank);
  const card = (title, abbr, sub) => {
    if (!abbr) return '';
    const t = d.teamsBy[abbr];
    const el = document.createElement('div');
    el.className = 'card';
    el.innerHTML = `<h3>${title}</h3>`;
    const big = document.createElement('div');
    big.className = 'big';
    big.appendChild(chip(t, 22));
    big.appendChild(Object.assign(document.createElement('a'),
      { href: `team.html?season=${d.season}&t=${abbr}`, textContent: t.name }));
    el.appendChild(big);
    el.insertAdjacentHTML('beforeend', `<div class="sub">${sub}</div>`);
    return el.outerHTML;
  };
  const top = byRank[0];
  const bottom = byRank[byRank.length - 1];
  const move = a => { const v = wk.teams[a].delta; return v > 0 ? `up ${v}` : v < 0 ? `down ${-v}` : 'unchanged'; };

  // Week 1 has nothing to move against, so lead with the ends of the board
  // instead of repeating the No. 1 team in three different cards.
  const used = new Set([top[0]]);
  if (n.biggest_riser) used.add(n.biggest_riser);
  if (n.biggest_faller) used.add(n.biggest_faller);
  const tightest = byRank
    .filter(([a]) => !used.has(a))
    .sort((a, b) => a[1].spread - b[1].spread)[0];

  const cards = [card('No. 1 overall', top[0], `Score ${top[1].avg} &middot; ${top[1].record}`)];
  if (n.biggest_riser && wk.teams[n.biggest_riser].delta > 0) {
    cards.push(card('Biggest riser', n.biggest_riser,
      `${move(n.biggest_riser)} to #${wk.teams[n.biggest_riser].rank}`));
    cards.push(card('Biggest faller', n.biggest_faller,
      `${move(n.biggest_faller)} to #${wk.teams[n.biggest_faller].rank}`));
  } else {
    cards.push(card('No. 32 overall', bottom[0], `Score ${bottom[1].avg}`));
    if (tightest) cards.push(card('Tightest consensus', tightest[0],
      `Every outlet within ${tightest[1].spread} spot${tightest[1].spread === 1 ? '' : 's'}`));
  }
  // "Most divisive" only means anything once two outlets can disagree.
  if (wk.sources.length > 1 && n.most_divisive) {
    cards.push(card('Most divisive', n.most_divisive,
      `Ranked #${wk.teams[n.most_divisive].high} to #${wk.teams[n.most_divisive].low} across outlets`));
  } else if (!used.has(bottom[0])) {
    cards.push(card('No. 32 overall', bottom[0], `Score ${bottom[1].avg} &middot; ${bottom[1].record}`));
  }
  $('cards').innerHTML = cards.slice(0, 4).join('');
}

function renderTable(wk, d, used) {
  const head = $('head');
  const cols = state.cols ? used : [];
  head.innerHTML = `
    <th class="l" style="width:34px">#</th>
    <th style="width:52px">Move</th>
    <th class="l">Team</th>
    <th>Rec</th>
    <th title="Average of every outlet's rank — lower is better">Score</th>
    <th title="Best and worst rank any single outlet gave">High/Low</th>
    <th class="l" title="Gap between the highest and lowest rank">Spread</th>
    ${cols.map(id => `<th class="src" title="${d.sourcesBy[id]?.name || id}">${shortName(d.sourcesBy[id]?.name || id)}</th>`).join('')}`;

  const rows = Object.entries(wk.teams)
    .sort((a, b) => a[1].rank - b[1].rank)
    .filter(([abbr]) => !state.filter || d.teamsBy[abbr].conference === state.filter);

  const maxSpread = Math.max(1, ...Object.values(wk.teams).map(t => t.spread));
  const frag = document.createDocumentFragment();

  for (const [abbr, t] of rows) {
    const team = d.teamsBy[abbr];
    const tr = document.createElement('tr');

    const rk = document.createElement('td');
    rk.className = 'l rk';
    rk.textContent = t.rank;
    tr.appendChild(rk);

    const mv = document.createElement('td');
    mv.appendChild(movement(t.delta));
    tr.appendChild(mv);

    const tc = document.createElement('td');
    tc.className = 'l';
    tc.appendChild(teamCell(team));
    tr.appendChild(tc);

    tr.appendChild(cell(t.record, ''));
    tr.appendChild(cell(t.avg.toFixed(2), 'score'));
    tr.appendChild(cell(`${t.high}–${t.low}`, ''));

    const sp = document.createElement('td');
    sp.className = 'l';
    sp.innerHTML = `<span class="spread"><span class="meter"><i style="width:${
      Math.round(t.spread / maxSpread * 100)}%"></i></span><span>${t.spread}</span></span>`;
    tr.appendChild(sp);

    for (const id of cols) {
      const td = document.createElement('td');
      td.className = 'src';
      const r = t.ranks[id];
      const dlt = t.source_delta?.[id];
      td.innerHTML = r == null ? '<span style="color:var(--muted)">–</span>' :
        `${r}${dlt ? ` <span style="font-size:10px;color:var(--${dlt > 0 ? 'up' : 'down'})">${
          dlt > 0 ? '▲' : '▼'}${Math.abs(dlt)}</span>` : ''}`;
      tr.appendChild(td);
    }
    frag.appendChild(tr);
  }
  $('rows').textContent = '';
  $('rows').appendChild(frag);
}

const cell = (text, cls) => {
  const td = document.createElement('td');
  td.className = cls;
  td.textContent = text;
  return td;
};

function renderSources(wk) {
  const items = wk.sources.map(s => `<li>
      <b>${s.name}</b>
      <span>${s.author ? s.author + ' · ' : ''}${fmtDate(s.published) || 'date n/a'}</span><br>
      <a href="${s.url}" target="_blank" rel="noopener">${(s.title || 'Read the article').slice(0, 72)}</a>
    </li>`);
  const misses = (wk.failed_sources || []).map(f => `<li class="warn">
      <b>${f.name}</b><span> not included this week</span><br>
      <span style="font-size:11.5px">${f.error}</span></li>`);
  $('srcList').innerHTML = items.join('') + misses.join('');
}
