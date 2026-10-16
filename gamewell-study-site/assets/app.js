(() => {
  const S = window.STUDY;
  const $ = (id) => document.getElementById(id);
  Object.entries(S.claims).forEach(([id, text]) => { const el = $('claim' + id); if (el) el.textContent = text; });

  const esc = (s) => String(s).replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const n = (s) => Number.parseFloat(s);
  const fmt = (x) => x.toString();

  function forest(el, rows, opts = {}) {
    const width = 900, rowH = opts.rowH || 42, left = opts.left || 220, right = 24, top = 32, bottom = 44;
    const vals = rows.flatMap(r => [n(r.lo), n(r.hi), 0, ...(opts.band ? [-.5,.5] : [])]);
    let min = Math.min(...vals), max = Math.max(...vals), pad = (max - min) * .10 || 1;
    min -= pad; max += pad;
    const height = top + rows.length * rowH + bottom;
    const x = v => left + ((v - min) / (max - min)) * (width - left - right);
    const zero = x(0);
    const ticks = [min, 0, max];
    const band = opts.band ? `<rect x="${x(-.5)}" y="${top-13}" width="${x(.5)-x(-.5)}" height="${rows.length*rowH+12}" fill="var(--band)"/><line x1="${x(-.5)}" x2="${x(-.5)}" y1="${top-13}" y2="${height-bottom+4}" stroke="var(--amber)" stroke-dasharray="4 4"/><line x1="${x(.5)}" x2="${x(.5)}" y1="${top-13}" y2="${height-bottom+4}" stroke="var(--amber)" stroke-dasharray="4 4"/>` : '';
    const label = opts.unitLabel ? `<text x="${left}" y="16" class="axis-title">${esc(opts.unitLabel)}</text>` : '';
    const axis = `<line x1="${left}" x2="${width-right}" y1="${height-bottom}" y2="${height-bottom}" stroke="var(--line)"/><line x1="${zero}" x2="${zero}" y1="${top-14}" y2="${height-bottom+4}" stroke="var(--ink)" stroke-width="1.4"/><g class="axis-labels">${ticks.map(t => `<text x="${x(t)}" y="${height-13}" text-anchor="${t===min?'start':t===max?'end':'middle'}">${fmt(t)}</text>`).join('')}</g>`;
    const items = rows.map((r,i) => { const y = top + i*rowH + rowH/2; const lo=x(n(r.lo)), hi=x(n(r.hi)), est=x(n(r.est)); const isOut = r.included === false; return `<g class="plot-row"><text x="8" y="${y+4}" class="row-label">${esc(r.label)}</text><line x1="${lo}" x2="${hi}" y1="${y}" y2="${y}" stroke="${isOut?'var(--muted)':'var(--teal)'}" stroke-width="4" stroke-linecap="round"/><line x1="${lo}" x2="${lo}" y1="${y-7}" y2="${y+7}" stroke="${isOut?'var(--muted)':'var(--teal)'}" stroke-width="2"/><line x1="${hi}" x2="${hi}" y1="${y-7}" y2="${y+7}" stroke="${isOut?'var(--muted)':'var(--teal)'}" stroke-width="2"/><circle cx="${est}" cy="${y}" r="7" fill="${isOut?'var(--muted)':'var(--coral)'}" stroke="var(--card)" stroke-width="3"><title>${esc(r.label)}: estimate ${esc(r.est)}; 95% interval ${esc(r.lo)} to ${esc(r.hi)}; ${esc(r.unit || opts.unitLabel || '')}</title></circle>${isOut ? '<text x="'+(width-right)+'" y="'+(y+4)+'" text-anchor="end" class="row-note">different unit / not in per-hour label</text>' : ''}</g>`; }).join('');
    el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="plot-title plot-desc"><title id="plot-title">${esc(opts.title || 'Forest plot')}</title><desc id="plot-desc">Each row shows an estimate and its 95% interval. The vertical line is zero.${opts.band?' The shaded region is plus or minus 0.5 in the per-hour unit.':''}</desc><style>.row-label{font:600 12px Inter,system-ui,sans-serif;fill:var(--ink)}.row-note{font:11px Inter,system-ui,sans-serif;fill:var(--muted)}.axis-labels{font:11px Inter,system-ui,sans-serif;fill:var(--muted)}.axis-title{font:700 11px Inter,system-ui,sans-serif;fill:var(--muted);letter-spacing:.06em}</style>${label}${band}${axis}${items}</svg>`;
  }

  forest($('primaryPlot'), [{label:'Primary within-person', est:S.primary.estimate, lo:S.primary.lower, hi:S.primary.upper, unit:S.primary.unit}], {band:true, unitLabel:'95% interval · points per hour', title:'Primary estimate'});
  const perHour = S.sensitivity.filter(r => r.unit === 'points per hour');
  forest($('hourPlot'), perHour.map(r => ({...r, label:r.label + (r.included ? ' · included' : '')})), {band:true, rowH:39, unitLabel:'points per hour', title:'Per-hour sensitivity analyses'});
  forest($('logPlot'), [S.sensitivity.find(r => r.id === '7b_i_log1p_minutes')], {rowH:52, unitLabel:'points per 1 SD of log exposure', title:'Log exposure sensitivity'});
  forest($('anyPlot'), [S.sensitivity.find(r => r.id === '7c_any_play')], {rowH:52, unitLabel:'points · any play vs none', title:'Any play comparison'});
  forest($('lifePlot'), [{label:'Life satisfaction · secondary', est:S.life.estimate, lo:S.life.lower, hi:S.life.upper, unit:S.life.unit}], {band:true, unitLabel:'95% interval · points per hour', title:'Life satisfaction secondary estimate'});

  $('cohortFlow').innerHTML = S.cohort.map((r, i) => `<div class="flow-node"><span class="flow-stage">${esc(r.stage)}</span><span class="flow-count"><span><strong>${esc(r.intervals)}</strong><small>intervals</small></span>${r.participants ? `<span><strong>${esc(r.participants)}</strong><small>participants</small></span>` : ''}</span></div>${i < S.cohort.length - 1 ? '<div class="flow-arrow" aria-hidden="true">↓</div>' : ''}`).join('');
  $('gapTable').innerHTML = `<table class="gap-table"><thead><tr><th>Cutoff</th><th>Eligible intervals</th><th>Participants</th><th>≥2</th><th>≥5</th></tr></thead><tbody>${S.gap.map(r => `<tr><td>${esc(r.cutoff)}</td><td>${esc(r.eligible)}</td><td>${esc(r.participants)}</td><td>${esc(r.at2)}</td><td>${esc(r.at5)}</td></tr>`).join('')}</tbody></table>`;
  $('ledgerTable').innerHTML = `<table class="ledger"><thead><tr><th>Stage</th><th>Analysis ID</th><th>Cohort</th><th>Status</th></tr></thead><tbody>${S.ledger.map(r => `<tr class="${r[3] === 'invalid-not used' ? 'invalid-not-used' : r[3] === 'reported' ? 'reported' : ''}"><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td>${esc(r[3])}</td></tr>`).join('')}</tbody></table>`;

  const theme = localStorage.getItem('gamewell-theme');
  if (theme === 'dark') document.documentElement.dataset.theme = 'dark';
  $('themeToggle').addEventListener('click', () => { const dark = document.documentElement.dataset.theme !== 'dark'; document.documentElement.dataset.theme = dark ? 'dark' : 'light'; $('themeToggle').setAttribute('aria-pressed', String(dark)); localStorage.setItem('gamewell-theme', dark ? 'dark' : 'light'); });

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const reveals = document.querySelectorAll('.reveal');
  if (reduce || !('IntersectionObserver' in window)) reveals.forEach(el => el.classList.add('is-visible'));
  else { const io = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); io.unobserve(entry.target); } }), {threshold:.12}); reveals.forEach(el => io.observe(el)); }
})();