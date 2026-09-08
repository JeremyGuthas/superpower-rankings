import {
  loadIndex, loadSeason, latestWeek, teamCell, movement, chip, fmtDate, initTheme,
  shortName, renderNav, gapChip, signed,
} from './app.js';

const $ = id => document.getElementById(id);
initTheme($('theme'));

const state = { data: null, week: null, group: 'outlets', filter: '' };

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

  renderNav($('nav'), 'index.html', season);
  const data = await loadSeason(season);
  state.data = data;
  $('divs').innerHTML = [...new Set(data.teams.map(t => t.division))].sort()
    .map(d => `<option value="div:${d}">${d}</option>`).join('');
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
  for (const [id, name] of [['gOutlets', 'outlets'], ['gContext', 'context']]) {
    $(id).onclick = () => { state.group = state.group === name ? 'none' : name; render(); };
  }
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

  const pad = String(state.week).padStart(2, '0');
  $('shareSvg').href = `share/week-${d.season}-${pad}.svg`;
  $('shareDigest').href = `share/digest-${d.season}-${pad}.html`;

  renderCards(wk, d);
  renderStories(wk, d);
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
  const outlets = state.group === 'outlets' ? used : [];
  const context = state.group === 'context';
  $('gOutlets').setAttribute('aria-pressed', String(state.group === 'outlets'));
  $('gContext').setAttribute('aria-pressed', String(context));
  const hasMarket = Object.values(wk.teams).some(t => t.market_rank);

  head.innerHTML = `
    <th class="l" style="width:34px">#</th>
    <th style="width:52px">Move</th>
    <th class="l">Team</th>
    <th>Rec</th>
    <th title="Average of every outlet's rank — lower is better">Score</th>
    <th title="Best and worst rank any single outlet gave">High/Low</th>
    <th class="l" title="Gap between the highest and lowest rank">Spread</th>
    ${outlets.map(id => `<th class="src" title="${d.sourcesBy[id]?.name || id}">${shortName(d.sourcesBy[id]?.name || id)}</th>`).join('')}
    ${context ? `
      <th class="l" title="The next opponent, with their Superpower rank">Next up</th>
      <th title="Average Superpower rank of the remaining opponents — lower is tougher">Rest SOS</th>
      <th title="Where results alone would rank this team">By record</th>
      <th title="Ranking minus record rank — positive means the media rates them above their results">Gap</th>
      ${hasMarket ? `<th title="Rank implied by Super Bowl odds">Market</th>
      <th title="Superpower rank minus market rank — positive means the market is higher on them">Edge</th>` : ''}
    ` : ''}`;

  const rows = Object.entries(wk.teams)
    .sort((a, b) => a[1].rank - b[1].rank)
    .filter(([abbr]) => matchesFilter(d.teamsBy[abbr]));

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

    for (const id of outlets) {
      const td = document.createElement('td');
      td.className = 'src';
      const r = t.ranks[id];
      const dlt = t.source_delta?.[id];
      td.innerHTML = r == null ? '<span style="color:var(--muted)">–</span>' :
        `${r}${dlt ? ` <span style="font-size:10px;color:var(--${dlt > 0 ? 'up' : 'down'})">${
          dlt > 0 ? '▲' : '▼'}${Math.abs(dlt)}</span>` : ''}`;
      tr.appendChild(td);
    }

    if (context) {
      const ng = t.next_game;
      const nx = document.createElement('td');
      nx.className = 'l';
      if (ng) {
        const opp = d.teamsBy[ng.opponent];
        nx.innerHTML = `${ng.home ? 'vs' : '@'} <a href="team.html?season=${d.season}&t=${
          ng.opponent}"><b>${opp.abbr}</b></a>` +
          (ng.opponent_rank ? ` <span class="flag">#${ng.opponent_rank}</span>` : '');
      } else {
        nx.innerHTML = '<span style="color:var(--muted)">season over</span>';
      }
      tr.appendChild(nx);

      tr.appendChild(cell(t.sos_remaining != null ? t.sos_remaining.toFixed(1) : '–', 'num'));
      tr.appendChild(cell(t.record_rank ?? '–', 'num'));

      const dv = document.createElement('td');
      dv.appendChild(gapChip(t.divergence ?? null));
      tr.appendChild(dv);

      if (hasMarket) {
        tr.appendChild(cell(t.market_rank ?? '–', 'num'));
        const mk = document.createElement('td');
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

function matchesFilter(team) {
  if (!state.filter) return true;
  if (state.filter.startsWith('div:')) return team.division === state.filter.slice(4);
  return team.conference === state.filter;
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


/* ---- storylines: the things only an aggregate can say ---- */

function renderStories(wk, d) {
  const s = wk.storylines || {};
  const name = a => d.teamsBy[a].name;
  const link = a => `<a href="team.html?season=${d.season}&t=${a}"><b>${name(a)}</b></a>`;

  fillLane('laneOutliers', s.outliers, o => {
    const outlet = d.sourcesBy[o.source]?.name || o.source;
    const side = o.gap > 0 ? 'higher' : 'lower';
    return `${link(o.team)} at <b>#${o.rank}</b> on ${outlet}
      <span class="why">${Math.abs(o.gap)} spots ${side} than the consensus #${o.consensus}</span>`;
  }, wk.sources.length < 3
      ? 'At least three outlets are needed before one can be called an outlier.'
      : 'Every outlet is within a few spots of the consensus this week.');

  fillLane('laneDiverge', s.divergent, v => {
    const side = v.gap > 0 ? 'ahead of' : 'behind';
    return `${link(v.team)} <span class="flag ${v.gap > 0 ? 'hot' : 'cold'}">${signed(v.gap)}</span>
      <span class="why">#${v.rank} in the rankings, #${v.record_rank} on results (${v.record})
      — rated ${Math.abs(v.gap)} spots ${side} what they have earned</span>`;
  }, wk.games_through
      ? 'No team is far from where its record puts it.'
      : 'No games played yet — this comparison starts once Week 1 is in the books.');

  const meta = s.market_meta;
  $('marketHead').textContent = meta?.provider
    ? `Media vs. the market (${meta.provider})` : 'Media vs. the market';
  fillLane('laneMarket', s.market, m => {
    const believer = m.gap > 0 ? 'the market' : 'the media';
    return `${link(m.team)} <span class="od">${m.odds}</span>
      <span class="why">#${m.rank} in the consensus, #${m.market_rank} at the book
      — ${believer} is the believer by ${Math.abs(m.gap)} spots</span>`;
  }, meta ? 'The board and the betting market broadly agree.'
          : 'Betting odds are not available for this week.');
}

function fillLane(id, items, render, empty) {
  const host = $(id);
  if (!items || !items.length) { host.innerHTML = `<li class="none">${empty}</li>`; return; }
  host.innerHTML = items.slice(0, 4).map(i => `<li>${render(i)}</li>`).join('');
}
