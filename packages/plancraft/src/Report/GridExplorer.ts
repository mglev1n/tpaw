import { GridReportData } from './GridReport'
import { STYLE, _esc } from './HtmlReport'

// Interactive companion to the static grid report: the same simulation
// results, but filterable by decision, re-rankable by metric, and drillable
// into a single combination's median trajectory across every condition.
//
// Self-contained: the whole result set is embedded as JSON and all
// interaction is client-side, so the file works offline and can be handed to
// someone else as a single attachment.

const EXPLORER_STYLE = `
main.wide { max-width: 1180px }
.controls { display: grid; gap: 14px }
.control-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px }
.control-label {
  flex: 0 0 132px; color: var(--text-secondary); font-size: 13px; font-weight: 600;
}
button.chip {
  font: inherit; font-size: 13px; padding: 4px 11px; border-radius: 999px;
  border: 1px solid var(--axis); background: transparent; color: var(--text-secondary);
  cursor: pointer;
}
button.chip:hover { border-color: var(--text-secondary) }
button.chip[aria-pressed="true"] {
  background: var(--text-primary); border-color: var(--text-primary);
  color: var(--page); font-weight: 600;
}
button.link {
  font: inherit; font-size: 13px; background: none; border: none; padding: 0;
  color: var(--text-secondary); text-decoration: underline; cursor: pointer;
}
.summary { margin: 14px 0 0; color: var(--text-secondary); font-size: 14px }
.summary strong { color: var(--text-primary) }
.table-scroll { overflow-x: auto; margin-top: 6px }
table.rank { min-width: 720px }
table.rank tbody tr { cursor: pointer }
table.rank tbody tr:hover td { background: rgba(127,127,127,0.08) }
table.rank tbody tr[aria-selected="true"] td {
  background: rgba(127,127,127,0.14); font-weight: 600;
}
td.rank-n, th.rank-n { color: var(--muted); width: 40px }
.detail-empty { color: var(--muted); font-size: 14px; margin: 0 }
.detail-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; margin: 0 0 4px }
.detail-head h3 { font-size: 15px; margin: 0 }
.pill {
  font-size: 12px; padding: 2px 9px; border-radius: 999px;
  background: rgba(127,127,127,0.14); color: var(--text-secondary);
}
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 14px }
@media (max-width: 760px) { .charts { grid-template-columns: 1fr } }
.chart-title { font-size: 13px; color: var(--text-secondary); margin: 0 0 4px }
.legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 12px; color: var(--text-secondary) }
svg text { fill: var(--text-secondary); font-size: 10px }
svg .line { fill: none; stroke-width: 2 }
svg .retire-line { stroke: var(--axis); stroke-width: 1; stroke-dasharray: 3 3 }
`

// Client-side logic. Written without template literals so it can be embedded
// in a TS template literal without escaping gymnastics.
const EXPLORER_SCRIPT = String.raw`
(function () {
  var D = window.__GRID__;
  var state = {
    condition: D.referenceConditionId,
    metric: 'spending',
    filters: {},
    selected: null,
  };
  D.dimensions.forEach(function (d) { state.filters[d.id] = null; });

  try {
    var saved = JSON.parse(localStorage.getItem('plancraft-explorer') || 'null');
    if (saved && saved.gridName === D.gridName) {
      if (saved.condition) state.condition = saved.condition;
      if (saved.metric) state.metric = saved.metric;
      if (saved.filters) {
        D.dimensions.forEach(function (d) {
          if (saved.filters[d.id]) state.filters[d.id] = saved.filters[d.id];
        });
      }
    }
  } catch (e) { /* storage unavailable; defaults are fine */ }

  var save = function () {
    try {
      localStorage.setItem('plancraft-explorer', JSON.stringify({
        gridName: D.gridName, condition: state.condition,
        metric: state.metric, filters: state.filters,
      }));
    } catch (e) { /* ignore */ }
  };

  var METRICS = {
    spending: {
      label: 'Lifestyle spending',
      get: function (r) { return r.medianRetirementSpending; },
      fmt: function (v) { return usd(v) + '/mo'; },
      higherIsBetter: true,
    },
    success: {
      label: 'Success probability',
      get: function (r) { return r.successProbability; },
      fmt: function (v) { return (v * 100).toFixed(1) + '%'; },
      higherIsBetter: true,
    },
    ending: {
      label: 'Ending balance',
      get: function (r) { return r.endingBalanceP50; },
      fmt: function (v) { return usdCompact(v); },
      higherIsBetter: true,
    },
    atRetirement: {
      label: 'Balance at retirement',
      get: function (r) { return r.medianBalanceAtRetirement; },
      fmt: function (v) { return usdCompact(v); },
      higherIsBetter: true,
    },
  };

  function usd(v) {
    return '$' + Math.round(v).toLocaleString('en-US');
  }
  function usdCompact(v) {
    var a = Math.abs(v);
    if (a >= 1e6) return '$' + (v / 1e6).toFixed(2).replace(/\.?0+$/, '') + 'M';
    if (a >= 1e3) return '$' + Math.round(v / 1e3) + 'k';
    return '$' + Math.round(v);
  }
  function el(id) { return document.getElementById(id); }

  function visibleRows() {
    return D.results.filter(function (r) {
      if (r.conditionId !== state.condition) return false;
      for (var i = 0; i < D.dimensions.length; i++) {
        var d = D.dimensions[i];
        var f = state.filters[d.id];
        if (f && f.indexOf(r.cells[d.id]) === -1) return false;
      }
      return true;
    });
  }

  function render() {
    renderControls();
    var rows = visibleRows();
    var m = METRICS[state.metric];
    rows.sort(function (a, b) { return m.get(b) - m.get(a); });
    renderSummary(rows, m);
    renderTable(rows, m);
    renderDetail();
    save();
  }

  function renderControls() {
    D.dimensions.forEach(function (d) {
      var f = state.filters[d.id];
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-dim="' + d.id + '"]'),
        function (btn) {
          var on = !f || f.indexOf(btn.getAttribute('data-variant')) !== -1;
          btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        }
      );
    });
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-condition]'),
      function (btn) {
        btn.setAttribute('aria-pressed',
          btn.getAttribute('data-condition') === state.condition ? 'true' : 'false');
      }
    );
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-metric]'),
      function (btn) {
        btn.setAttribute('aria-pressed',
          btn.getAttribute('data-metric') === state.metric ? 'true' : 'false');
      }
    );
  }

  function renderSummary(rows, m) {
    var total = D.results.filter(function (r) {
      return r.conditionId === state.condition;
    }).length;
    if (!rows.length) {
      el('summary').innerHTML = 'No combinations match these filters.';
      return;
    }
    var values = rows.map(m.get).sort(function (a, b) { return a - b; });
    var median = values[Math.floor(values.length / 2)];
    el('summary').innerHTML =
      '<strong>' + rows.length + '</strong> of ' + total + ' combinations · ' +
      m.label + ': best <strong>' + m.fmt(values[values.length - 1]) +
      '</strong> · median <strong>' + m.fmt(median) +
      '</strong> · worst <strong>' + m.fmt(values[0]) + '</strong>';
  }

  var MAX_ROWS = 250;

  function renderTable(rows, m) {
    var shown = rows.slice(0, MAX_ROWS);
    var head = '<tr><th class="rank-n">#</th>' +
      D.dimensions.map(function (d) { return '<th>' + d.name + '</th>'; }).join('') +
      '<th>' + m.label + '</th><th>Success</th><th>Ending</th></tr>';
    var body = shown.map(function (r, i) {
      var sel = state.selected === r.name ? ' aria-selected="true"' : '';
      return '<tr data-combo="' + encodeURIComponent(r.name) + '"' + sel + '>' +
        '<td class="rank-n">' + (i + 1) + '</td>' +
        D.dimensions.map(function (d) {
          return '<td>' + (r.cellNames[d.id] || r.cells[d.id]) + '</td>';
        }).join('') +
        '<td>' + m.fmt(m.get(r)) + '</td>' +
        '<td>' + (r.successProbability * 100).toFixed(1) + '%</td>' +
        '<td>' + usdCompact(r.endingBalanceP50) + '</td>' +
        '</tr>';
    }).join('');
    el('rank-head').innerHTML = head;
    el('rank-body').innerHTML = body;
    el('truncated').textContent = rows.length > MAX_ROWS
      ? 'Showing the top ' + MAX_ROWS + ' of ' + rows.length + ' matching combinations.'
      : '';
    Array.prototype.forEach.call(el('rank-body').querySelectorAll('tr'), function (tr) {
      tr.addEventListener('click', function () {
        var name = decodeURIComponent(tr.getAttribute('data-combo'));
        state.selected = state.selected === name ? null : name;
        render();
      });
    });
  }

  function seriesColor(i) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue('--series-' + ((i % 6) + 1)).trim() || '#666';
  }

  function lineChart(points, opts) {
    // points: array of {label, values:[]} sharing one x index space.
    var W = 460, H = 190, ml = 52, mr = 10, mt = 10, mb = 26;
    var n = opts.numYears;
    var allValues = [];
    points.forEach(function (p) { allValues = allValues.concat(p.values); });
    var max = Math.max.apply(null, allValues.concat([0]));
    var min = Math.min.apply(null, allValues.concat([0]));
    if (max === min) max = min + 1;
    var x = function (i) { return ml + (i / Math.max(1, n - 1)) * (W - ml - mr); };
    var y = function (v) { return mt + (1 - (v - min) / (max - min)) * (H - mt - mb); };

    var ticks = [];
    for (var t = 0; t <= 4; t++) ticks.push(min + ((max - min) * t) / 4);

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
      opts.title + '">';
    ticks.forEach(function (v) {
      svg += '<line class="grid" x1="' + ml + '" y1="' + y(v).toFixed(1) +
        '" x2="' + (W - mr) + '" y2="' + y(v).toFixed(1) + '"/>';
      svg += '<text x="' + (ml - 6) + '" y="' + (y(v) + 3).toFixed(1) +
        '" text-anchor="end">' + opts.fmtY(v) + '</text>';
    });
    if (opts.retireIndex >= 0 && opts.retireIndex < n) {
      svg += '<line class="retire-line" x1="' + x(opts.retireIndex).toFixed(1) +
        '" y1="' + mt + '" x2="' + x(opts.retireIndex).toFixed(1) +
        '" y2="' + (H - mb) + '"/>';
      svg += '<text x="' + (x(opts.retireIndex) + 4).toFixed(1) + '" y="' +
        (mt + 9) + '">retire</text>';
    }
    points.forEach(function (p, pi) {
      var d = p.values.map(function (v, i) {
        return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1);
      }).join(' ');
      svg += '<path class="line" d="' + d + '" stroke="' + seriesColor(pi) + '"/>';
    });
    for (var k = 0; k <= 4; k++) {
      var i2 = Math.round((k / 4) * (n - 1));
      svg += '<text x="' + x(i2).toFixed(1) + '" y="' + (H - 8) +
        '" text-anchor="middle">' + (D.timeline.anchorYear + i2) + '</text>';
    }
    svg += '<line class="axis" x1="' + ml + '" y1="' + (H - mb) + '" x2="' +
      (W - mr) + '" y2="' + (H - mb) + '"/>';
    svg += '</svg>';
    return svg;
  }

  function renderDetail() {
    var host = el('detail');
    if (!state.selected) {
      host.innerHTML = '<p class="detail-empty">Select a row above to see how ' +
        'that combination plays out over time, in every condition.</p>';
      return;
    }
    var runs = D.results.filter(function (r) { return r.name === state.selected; });
    if (!runs.length) { host.innerHTML = ''; return; }
    var byCondition = D.conditions.map(function (c) {
      return { condition: c, run: runs.find(function (r) { return r.conditionId === c.id; }) };
    }).filter(function (x) { return !!x.run; });

    var current = runs.find(function (r) { return r.conditionId === state.condition; }) || runs[0];
    var html = '<div class="detail-head"><h3>' + current.name + '</h3>' +
      D.dimensions.map(function (d) {
        return '<span class="pill">' + d.name + ': ' +
          (current.cellNames[d.id] || current.cells[d.id]) + '</span>';
      }).join('') + '</div>';

    html += '<div class="table-scroll"><table class="num"><tr><th>Condition</th>' +
      '<th>Lifestyle spending</th><th>Success</th><th>At retirement</th><th>Ending</th></tr>' +
      byCondition.map(function (x) {
        var r = x.run;
        var mark = x.condition.id === state.condition ? ' ←' : '';
        return '<tr><td>' + x.condition.name + mark + '</td><td>' +
          usd(r.medianRetirementSpending) + '/mo</td><td>' +
          (r.successProbability * 100).toFixed(1) + '%</td><td>' +
          usdCompact(r.medianBalanceAtRetirement) + '</td><td>' +
          usdCompact(r.endingBalanceP50) + '</td></tr>';
      }).join('') + '</table></div>';

    var numYears = D.timeline.numYears;
    var balanceSeries = byCondition.map(function (x) {
      return { label: x.condition.name, values: x.run.balanceByYear };
    });
    var spendingSeries = byCondition.map(function (x) {
      return { label: x.condition.name, values: x.run.spendingByYear };
    });

    html += '<div class="charts">';
    var retireIndex = current.retireYear;
    html += '<div><p class="chart-title">Portfolio balance (median, real)</p>' +
      lineChart(balanceSeries, {
        title: 'Portfolio balance by year',
        numYears: numYears,
        retireIndex: retireIndex,
        fmtY: function (v) { return v >= 1000 ? '$' + (v / 1000).toFixed(1) + 'M' : '$' + Math.round(v) + 'k'; },
      }) + '</div>';
    html += '<div><p class="chart-title">Lifestyle spending (median, real $/mo)</p>' +
      lineChart(spendingSeries, {
        title: 'Lifestyle spending by year',
        numYears: numYears,
        retireIndex: retireIndex,
        fmtY: function (v) { return '$' + Math.round(v / 1000) + 'k'; },
      }) + '</div>';
    html += '</div>';

    html += '<div class="legend">' + byCondition.map(function (x, i) {
      return '<span><span class="key" style="background:' + seriesColor(i) +
        '"></span>' + x.condition.name + '</span>';
    }).join('') + '</div>';

    host.innerHTML = html;
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!(t instanceof HTMLElement)) return;
    if (t.hasAttribute('data-condition')) {
      state.condition = t.getAttribute('data-condition');
      render();
    } else if (t.hasAttribute('data-metric')) {
      state.metric = t.getAttribute('data-metric');
      render();
    } else if (t.hasAttribute('data-dim')) {
      var dim = t.getAttribute('data-dim');
      var variant = t.getAttribute('data-variant');
      var all = D.dimensions.find(function (d) { return d.id === dim; });
      var allIds = Object.keys(all.variantNames);
      var f;
      if (!state.filters[dim]) {
        // Nothing filtered yet: first click isolates that choice, which is
        // what you want when pinning a decision you have already made.
        f = [variant];
      } else {
        f = state.filters[dim].slice();
        var idx = f.indexOf(variant);
        if (idx === -1) f = f.concat([variant]);
        else if (f.length > 1) f = f.slice(0, idx).concat(f.slice(idx + 1));
        else f = allIds.slice(); // clicking the last remaining chip clears it
      }
      state.filters[dim] = f.length === allIds.length ? null : f;
      render();
    } else if (t.id === 'reset') {
      D.dimensions.forEach(function (d) { state.filters[d.id] = null; });
      state.selected = null;
      render();
    }
  });

  render();
})();
`

export const getGridExplorerHtml = (data: GridReportData): string => {
  const chips = (
    label: string,
    items: { id: string; name: string }[],
    attr: string,
  ) =>
    `<div class="control-row"><span class="control-label">${_esc(label)}</span>` +
    items
      .map(
        (x) =>
          `<button class="chip" ${attr}="${_esc(x.id)}">${_esc(x.name)}</button>`,
      )
      .join('') +
    `</div>`

  const filterRows = data.dimensions
    .map((d) =>
      [
        `<div class="control-row"><span class="control-label">${_esc(d.name)}</span>`,
        ...Object.entries(d.variantNames).map(
          ([id, name]) =>
            `<button class="chip" data-dim="${_esc(d.id)}" data-variant="${_esc(id)}">${_esc(name)}</button>`,
        ),
        `</div>`,
      ].join(''),
    )
    .join('')

  // Embedded as JSON; "<" is escaped so a stray "</script>" in any label
  // cannot terminate the script element early.
  const payload = JSON.stringify(data).replace(/</g, '\\u003c')

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${_esc(data.gridName)} — explorer</title>
<style>${STYLE}${EXPLORER_STYLE}</style>
</head><body><main class="wide">
<h1>${_esc(data.gridName)}</h1>
<p class="sub">Interactive explorer · ${data.results.length} simulations across ${data.conditions.length} condition(s)</p>
${data.gridDescription ? `<p class="sub">${_esc(data.gridDescription)}</p>` : ''}

<section class="card">
  <div class="controls">
    ${chips('Condition', data.conditions, 'data-condition')}
    ${chips(
      'Rank by',
      [
        { id: 'spending', name: 'Lifestyle spending' },
        { id: 'success', name: 'Success probability' },
        { id: 'ending', name: 'Ending balance' },
        { id: 'atRetirement', name: 'Balance at retirement' },
      ],
      'data-metric',
    )}
    ${filterRows}
    <div class="control-row"><span class="control-label"></span>
      <button class="link" id="reset">Reset filters and selection</button>
    </div>
  </div>
  <p class="summary" id="summary"></p>
</section>

<h2>Ranked combinations</h2>
<section class="card">
  <div class="table-scroll">
    <table class="rank num">
      <thead id="rank-head"></thead>
      <tbody id="rank-body"></tbody>
    </table>
  </div>
  <p class="delta" id="truncated"></p>
</section>

<h2>Detail</h2>
<section class="card" id="detail"></section>

<script>window.__GRID__ = ${payload};</script>
<script>${EXPLORER_SCRIPT}</script>
</main></body></html>`
}
