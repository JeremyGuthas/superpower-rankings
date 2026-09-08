import {
  loadIndex, loadSeason, fmtDate, initTheme, renderNav, rankChart, OUTLET_COLORS,
} from './app.js';

const $ = id => document.getElementById(id);
initTheme($('theme'));

const st = { data: null, hidden: new Set() };

boot().catch(err => { $('verdict').textContent = err.message; });

async function boot() {
  const url = new URL(location.href);
  const idx = await loadIndex();
  const seasons = idx.seasons.map(s => s.season);
  const asked = Number(url.searchParams.get('season'));
  const season = seasons.includes(asked) ? asked : idx.default_season;
  $('season').innerHTML = seasons.map(y => `<option value="${y}">${y} season</option>`).join('');
  $('season').value = season;
  $('season').onchange = e => { location.href = `accuracy.html?season=${e.target.value}`; };
  renderNav($('nav'), 'accuracy.html', season);

  st.data = await loadSeason(season);
  addEventListener('resize', drawChart);
  render();
}

function render() {
  const d = st.data, a = d.accuracy || {};
  $('stamp').textContent = `Data compiled ${fmtDate(d.generated)}.`;
  $('meta').innerHTML = `${d.season} season &middot; ${d.weeks.length} week${
    d.weeks.length === 1 ? '' : 's'} of rankings`;

  if (!a.available) {
    $('basis').textContent = 'not scorable yet';
    $('verdict').innerHTML = `<b>Nothing to score yet.</b> ${
      a.reason || 'Outlets can only be graded once games have been played.'} ` +
      `Come back once the season is under way — every ranking published in the meantime ` +
      `is stored and will be scored retroactively.`;
    $('rows').innerHTML = '<tr><td class="empty" colspan="8">No completed games yet.</td></tr>';
    $('chart').innerHTML = '';
    return;
  }

  $('basis').textContent = a.basis;
  renderVerdict(a);
  renderTable(a);
  renderLegend(a);
  drawChart();
}

function renderVerdict(a) {
  const c = a.consensus, s = a.summary;
  if (!c || !s) { $('verdict').textContent = ''; return; }
  const beaten = s.outlets_that_beat_it.length;
  const names = id => (a.sources.find(r => r.id === id) || {}).name || id;
  if (s.outlets_scored < 2) {
    $('verdict').innerHTML = `<b>Only one outlet is scored for this season</b>, so the consensus ` +
      `is that outlet — averaging has nothing to average yet. It came in ` +
      `<b>${c.mae}</b> places off on the typical team.`;
    return;
  }
  $('verdict').innerHTML = beaten === 0
    ? `<b>The average beat every outlet that fed it.</b> The Superpower consensus finished
       <b>${c.mae}</b> places off on the typical team — closer than all ${s.outlets_scored}
       outlets scored. This is the case for aggregating in one line.`
    : `<b>${beaten} of ${s.outlets_scored} outlets beat the average.</b> The consensus finished
       <b>${c.mae}</b> places off on the typical team; ${
        s.outlets_that_beat_it.map(names).map(n => `<b>${n}</b>`).join(', ')} did better.`;
}

function renderTable(a) {
  const rows = [...a.sources];
  const worst = Math.max(...rows.map(r => r.mae), a.consensus?.mae ?? 0) || 1;
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
  $('rows').textContent = '';
  if (a.consensus) $('rows').appendChild(line(a.consensus, true));
  rows.forEach(r => $('rows').appendChild(line(r, false)));
}

function renderLegend(a) {
  const entries = [['consensus', 'Superpower consensus', 'var(--ink)'],
    ...a.sources.map((r, i) => [r.id, r.name, OUTLET_COLORS[i % OUTLET_COLORS.length]])];
  $('legend').textContent = '';
  for (const [id, label, color] of entries) {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('aria-pressed', String(!st.hidden.has(id)));
    b.innerHTML = `<span class="swatch" style="background:${color}"></span>${label}`;
    b.onclick = () => {
      st.hidden.has(id) ? st.hidden.delete(id) : st.hidden.add(id);
      b.setAttribute('aria-pressed', String(!st.hidden.has(id)));
      drawChart();
    };
    $('legend').appendChild(b);
  }
}

function drawChart() {
  const a = st.data.accuracy || {};
  if (!a.available) return;
  const all = [a.consensus, ...a.sources].filter(Boolean);
  const xs = [...new Set(all.flatMap(r => r.by_week.map(p => p.week)))].sort((x, y) => x - y);
  const peak = Math.max(...all.flatMap(r => r.by_week.map(p => p.mae ?? 0)));
  const top = Math.max(2, Math.ceil(peak));

  const series = all
    .filter(r => !st.hidden.has(r.id))
    .map((r, i) => ({
      label: r.name,
      color: r.id === 'consensus'
        ? (getComputedStyle(document.body).getPropertyValue('--ink').trim() || '#111')
        : OUTLET_COLORS[a.sources.findIndex(s => s.id === r.id) % OUTLET_COLORS.length],
      width: r.id === 'consensus' ? 2.75 : 1.7,
      dash: r.id === 'consensus' ? null : '4 3',
      dots: r.id === 'consensus',
      points: r.by_week.filter(p => p.mae != null).map(p => ({ x: p.week, y: p.mae })),
    }));

  const step = top <= 6 ? 1 : Math.ceil(top / 5);
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  rankChart($('chart'), series, {
    xs, yMin: 0, yMax: top, ticks, invert: false, height: 300,
    yLabel: 'Average ranking error by week, in places',
  });
}
