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
  el.style.color = onColor(team.primary);
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

/** A coloured gap chip: positive is good-news green by default. */
export function gapChip(value, { positive = 'up', suffix = '' } = {}) {
  const el = document.createElement('span');
  if (value === null || value === undefined) { el.className = 'mv flat'; el.textContent = '–'; return el; }
  const good = value > 0 ? positive === 'up' : positive === 'down';
  el.className = value === 0 ? 'mv flat' : `mv ${good ? 'up' : 'down'}`;
  el.textContent = value === 0 ? '–' : signed(value) + suffix;
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
export function rankChart(host, series, {
  xs, yMin = 1, yMax = 32, height = 300, invert = true,
  ticks = null, yLabel = null,
} = {}) {
  host.textContent = '';
  const W = Math.max(host.clientWidth || 640, 320);
  const H = height;
  const m = { t: 12, r: 14, b: 26, l: 30 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xsAll = xs && xs.length ? xs : [1];
  const xMin = Math.min(...xsAll), xMax = Math.max(...xsAll);
  const X = v => m.l + (xMax === xMin ? iw / 2 : (v - xMin) / (xMax - xMin) * iw);
  const span = (yMax - yMin) || 1;
  // invert:true puts the best value (rank 1) at the top, which is the only
  // way a rankings line reads correctly; error charts want 0 at the bottom.
  const Y = v => invert
    ? m.t + (v - yMin) / span * ih
    : m.t + ih - (v - yMin) / span * ih;

  const svg = mk('svg', {
    viewBox: `0 0 ${W} ${H}`, width: '100%', height: H,
    role: 'img', 'aria-label': yLabel || 'Ranking by week',
  });

  const rows = ticks || [1, 8, 16, 24, 32].filter(r => r >= yMin && r <= yMax);
  for (const r of rows) {
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
        title.textContent = `${s.label} — Week ${p.x}: ${invert ? '#' : ''}${p.y}`;
        c.appendChild(title);
        svg.appendChild(c);
      }
    }
  }
  host.appendChild(svg);
}

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
export const luminance = hex => {
  const [r, g, b] = _rgb(hex);
  return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b);
};

const _mix = (hex, towards, amount) => {
  const a = _rgb(hex), b = _rgb(towards);
  const out = a.map((v, i) => Math.round(v + (b[i] - v) * amount));
  return '#' + out.map(v => v.toString(16).padStart(2, '0')).join('');
};

export const isDarkTheme = () => {
  const set = document.documentElement.dataset.theme;
  if (set) return set === 'dark';
  return matchMedia('(prefers-color-scheme: dark)').matches;
};

/** Nudge a team colour until it reads against the current page background. */
export function readable(hex) {
  if (!hex) return 'currentColor';
  const l = luminance(hex);
  if (isDarkTheme()) return l < 0.22 ? _mix(hex, '#ffffff', 0.52) : hex;
  return l > 0.55 ? _mix(hex, '#000000', 0.38) : hex;
}

/** Black or white, whichever is legible on top of `hex`. */
export const onColor = hex => (luminance(hex) > 0.42 ? '#101820' : '#ffffff');

/** The one place the nav is defined, so every page carries the same one. */
export const NAV = [
  ['index.html', 'Rankings'],
  ['compare.html', 'Compare'],
  ['accuracy.html', 'Outlet accuracy'],
];

export function renderNav(host, current, season) {
  const q = season ? `?season=${season}` : '';
  host.insertAdjacentHTML('afterbegin', NAV.map(([href, label]) =>
    `<a href="${href}${q}"${href === current ? ' aria-current="page"' : ''}>${label}</a>`).join(''));
}

/** Signed value with an explicit sign, for gap columns. */
export const signed = n => (n > 0 ? `+${n}` : String(n));

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
