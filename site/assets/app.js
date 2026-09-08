/* Shared data access, formatting and chart helpers. */

const DATA = '../data';

export async function loadIndex() {
  const res = await fetch(`${DATA}/index.json`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`could not load the data index (${res.status}).
    Run "python -m superpower.run" to build it.`);
  return res.json();
}

export async function loadSeason(season) {
  const url = `${DATA}/season-${season}.json`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`could not load ${url} (${res.status})`);
  const data = await res.json();
  data.teamsBy = Object.fromEntries(data.teams.map(t => [t.abbr, t]));
  data.sourcesBy = Object.fromEntries(data.sources.map(s => [s.id, s]));
  data.weeksBy = Object.fromEntries(data.weeks.map(w => [w.week, w]));
  return data;
}

export const latestWeek = d => Math.max(...d.weeks.map(w => w.week));

/* ---------- formatting ---------- */

export function chip(team, size) {
  const el = document.createElement('span');
  el.className = 'chip';
  el.style.background = team.primary;
  el.style.boxShadow = `inset 0 0 0 1.5px ${team.secondary}`;
  el.textContent = team.abbr;
  if (size) { el.style.width = el.style.height = el.style.flexBasis = size + 'px'; }
  const img = new Image();
  img.alt = '';
  img.loading = 'lazy';
  img.src = `https://a.espncdn.com/i/teamlogos/nfl/500/${team.abbr.toLowerCase()}.png`;
  img.onerror = () => img.remove();       // falls back to the colour chip
  el.appendChild(img);
  return el;
}

export function teamCell(team, { division = true, link = true } = {}) {
  const wrap = document.createElement(link ? 'a' : 'span');
  wrap.className = 'team';
  if (link) wrap.href = `team.html?t=${team.abbr}`;
  wrap.appendChild(chip(team));
  const txt = document.createElement('span');
  txt.innerHTML = `<span class="nm">${team.name}</span>` +
    (division ? ` <span class="div">${team.division}</span>` : '');
  wrap.appendChild(txt);
  return wrap;
}

/** Movement badge. `delta` is positive when a team moved UP the board. */
export function movement(delta, { newLabel = 'NEW' } = {}) {
  const el = document.createElement('span');
  if (delta === null || delta === undefined) {
    el.className = 'mv new';
    el.textContent = newLabel;
  } else if (delta > 0) {
    el.className = 'mv up';
    el.textContent = `▲ ${delta}`;
  } else if (delta < 0) {
    el.className = 'mv down';
    el.textContent = `▼ ${Math.abs(delta)}`;
  } else {
    el.className = 'mv flat';
    el.textContent = '–';
  }
  return el;
}

export const ordinal = n =>
  n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');

export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d) ? '' : d.toLocaleDateString('en-US',
    { month: 'short', day: 'numeric', year: 'numeric' });
}

/* ---------- theme ---------- */

export function initTheme(btn) {
  const KEY = 'spr-theme';
  let stored = null;
  try { stored = localStorage.getItem(KEY); } catch { /* private mode */ }
  if (stored) document.documentElement.dataset.theme = stored;
  if (!btn) return;
  btn.addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    const next = dark ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  });
}

/* ---------- line chart ---------- */

const SVG = 'http://www.w3.org/2000/svg';
const mk = (tag, attrs = {}) => {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};

/**
 * Rank-over-time chart. Y axis is inverted (rank 1 at the top), which is the
 * only way a rankings line reads correctly.
 *
 * series: [{ id, label, color, width, points: [{x, y}], dots }]
 */
export function rankChart(host, series, { xs, yMax = 32, height = 300 } = {}) {
  host.textContent = '';
  const W = Math.max(host.clientWidth || 640, 320);
  const H = height;
  const m = { t: 12, r: 14, b: 26, l: 30 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xsAll = xs && xs.length ? xs : [1];
  const xMin = Math.min(...xsAll), xMax = Math.max(...xsAll);
  const X = v => m.l + (xMax === xMin ? iw / 2 : (v - xMin) / (xMax - xMin) * iw);
  const Y = v => m.t + (v - 1) / (yMax - 1) * ih;

  const svg = mk('svg', {
    viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
    role: 'img', 'aria-label': 'Ranking by week',
  });

  for (const r of [1, 8, 16, 24, 32].filter(r => r <= yMax)) {
    svg.appendChild(mk('line', { class: 'grid', x1: m.l, x2: W - m.r, y1: Y(r), y2: Y(r) }));
    const t = mk('text', { class: 'axis', x: m.l - 7, y: Y(r) + 3.5, 'text-anchor': 'end' });
    t.textContent = r;
    svg.appendChild(t);
  }
  for (const x of xsAll) {
    const t = mk('text', { class: 'axis', x: X(x), y: H - 8, 'text-anchor': 'middle' });
    t.textContent = x;
    svg.appendChild(t);
  }

  for (const s of series) {
    const pts = (s.points || []).filter(p => p.y != null);
    if (!pts.length) continue;
    const d = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ');
    svg.appendChild(mk('path', {
      d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      'stroke-opacity': s.opacity ?? 1,
      ...(s.dash ? { 'stroke-dasharray': s.dash } : {}),
    }));
    if (s.dots) {
      for (const p of pts) {
        const c = mk('circle', { cx: X(p.x), cy: Y(p.y), r: 3.5, fill: s.color,
          stroke: 'var(--card)', 'stroke-width': 1.5 });
        const title = mk('title');
        title.textContent = `${s.label} — Week ${p.x}: #${p.y}`;
        c.appendChild(title);
        svg.appendChild(c);
      }
    }
  }
  host.appendChild(svg);
}

/** Column-width-friendly outlet labels. */
export const shortName = n => n
  .replace('Sharp Football Analysis', 'Sharp')
  .replace('Bleacher Report', 'B/R')
  .replace(' Sports', '');

/* Distinct, colour-blind-safe hues for the per-outlet lines. */
export const OUTLET_COLORS = [
  '#e07b39', '#4b9cd3', '#7a5195', '#2e8b6f', '#c2185b',
  '#8a8f2b', '#0f6f8f', '#a34a2a',
];
