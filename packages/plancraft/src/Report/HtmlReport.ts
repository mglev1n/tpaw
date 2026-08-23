import _ from 'lodash'
import { CompareData, ScenarioCompare, YearlySeries } from './CompareData'
import { ScenarioError } from '../Compile/ResolveScenario'

// Self-contained comparison report: inline SVG + a small tooltip script, no
// external dependencies. Colors follow the dataviz reference palette
// (validated fixed-order categorical slots; sequential blue for fan charts).

const CATEGORICAL_LIGHT = [
  '#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948',
]
const CATEGORICAL_DARK = [
  '#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767',
]

const W = 860
const H = 320
const MARGIN = { top: 16, right: 130, bottom: 34, left: 64 }

export const _esc = (x: string) =>
  x.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export const _usd = (x: number) =>
  '$' + Math.round(x).toLocaleString('en-US')

export const _usdCompact = (x: number): string => {
  const abs = Math.abs(x)
  if (abs >= 1e6) return `$${(x / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`
  if (abs >= 1e3) return `$${(x / 1e3).toFixed(0)}K`
  return `$${x.toFixed(0)}`
}

export const _pct = (x: number) => `${(x * 100).toFixed(1)}%`

const _niceMax = (x: number): number => {
  if (x <= 0) return 1
  const exp = Math.pow(10, Math.floor(Math.log10(x)))
  const mantissa = x / exp
  const nice = mantissa <= 1 ? 1 : mantissa <= 2 ? 2 : mantissa <= 2.5 ? 2.5 : mantissa <= 5 ? 5 : 10
  return nice * exp
}

// Clean-valued y ticks: a 1/2/2.5/5-stepped increment covering [0, yMax].
const _niceTicks = (yMax: number): number[] => {
  const rawStep = yMax / 4
  const exp = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const mantissa = rawStep / exp
  const step =
    (mantissa <= 1 ? 1 : mantissa <= 2 ? 2 : mantissa <= 2.5 ? 2.5 : mantissa <= 5 ? 5 : 10) * exp
  return _.range(0, yMax + step / 2, step)
}

type ChartSeries = { label: string; color: number; data: number[] }

// A multi-series yearly line chart with hairline grid, direct end labels,
// legend, and a crosshair tooltip (wired up by the shared script via
// data-chart JSON).
const _lineChartSvg = (
  id: string,
  series: ChartSeries[],
  anchorYear: number,
  ageAtYear0: number,
  markerYearIndex: number | null,
  yLabel: string,
): string => {
  const numYears = Math.max(...series.map((s) => s.data.length))
  const yMax = _niceMax(Math.max(1, ...series.flatMap((s) => s.data)))
  const plotW = W - MARGIN.left - MARGIN.right
  const plotH = H - MARGIN.top - MARGIN.bottom
  const x = (yearIndex: number) => MARGIN.left + (yearIndex / (numYears - 1)) * plotW
  const y = (value: number) => MARGIN.top + plotH - (value / yMax) * plotH

  const yTicks = _niceTicks(yMax)
  const xTickEvery = numYears > 60 ? 20 : numYears > 30 ? 10 : 5
  const xTicks = _.range(0, numYears, xTickEvery)

  const grid = yTicks
    .map(
      (v) =>
        `<line x1="${MARGIN.left}" x2="${W - MARGIN.right}" y1="${y(v)}" y2="${y(v)}" class="grid"/>` +
        `<text x="${MARGIN.left - 8}" y="${y(v) + 4}" class="tick" text-anchor="end">${_usdCompact(v)}</text>`,
    )
    .join('')
  const xAxis =
    xTicks
      .map(
        (yi) =>
          `<text x="${x(yi)}" y="${H - 10}" class="tick" text-anchor="middle">${anchorYear + yi}</text>`,
      )
      .join('') +
    `<line x1="${MARGIN.left}" x2="${W - MARGIN.right}" y1="${MARGIN.top + plotH}" y2="${MARGIN.top + plotH}" class="axis"/>`

  const marker =
    markerYearIndex !== null && markerYearIndex > 0 && markerYearIndex < numYears
      ? `<line x1="${x(markerYearIndex)}" x2="${x(markerYearIndex)}" y1="${MARGIN.top}" y2="${MARGIN.top + plotH}" class="marker"/>` +
        `<text x="${x(markerYearIndex)}" y="${MARGIN.top + 10}" class="tick" text-anchor="middle">retirement</text>`
      : ''

  const paths = series
    .map((s) => {
      const d = s.data
        .map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
        .join('')
      return `<path d="${d}" class="line" style="stroke: var(--series-${s.color + 1})"/>`
    })
    .join('')

  // Direct end labels for up to 4 series; nudge collisions apart minimally
  // and connect with leader lines when nudged.
  const endLabels = block(() => {
    if (series.length > 4) return ''
    const items = series
      .map((s) => ({
        label: s.label,
        color: s.color,
        yPos: y(s.data[s.data.length - 1] ?? 0),
      }))
      .sort((a, b) => a.yPos - b.yPos)
    for (let i = 1; i < items.length; i++) {
      const prev = items[i - 1]!
      const curr = items[i]!
      if (curr.yPos - prev.yPos < 14) curr.yPos = prev.yPos + 14
    }
    return items
      .map(
        (item) =>
          `<circle cx="${W - MARGIN.right + 6}" cy="${item.yPos}" r="4" style="fill: var(--series-${item.color + 1})" class="ring"/>` +
          `<text x="${W - MARGIN.right + 14}" y="${item.yPos + 4}" class="endlabel">${_esc(item.label)}</text>`,
      )
      .join('')
  })

  const chartData = _esc(
    JSON.stringify({
      anchorYear,
      ageAtYear0,
      numYears,
      yMax,
      margin: MARGIN,
      w: W,
      h: H,
      series: series.map((s) => ({ label: s.label, color: s.color, data: s.data })),
    }),
  )

  return (
    `<div class="chart-wrap" id="${id}">` +
    `<svg viewBox="0 0 ${W} ${H}" class="pc-chart" role="img" aria-label="${_esc(yLabel)}" data-chart="${chartData}">` +
    grid +
    xAxis +
    marker +
    paths +
    endLabels +
    `<line class="crosshair" x1="0" x2="0" y1="${MARGIN.top}" y2="${MARGIN.top + plotH}" style="display:none"/>` +
    `</svg><div class="tooltip" style="display:none"></div></div>`
  )
}

const block = <T>(fn: () => T): T => fn()

// Per-scenario fan chart: p5-p95 and p25-p75 washes plus the median line,
// all in sequential blue (one series, magnitude bands - no legend box).
const _fanChartSvg = (
  scenario: ScenarioCompare,
  yMaxShared: number,
  percentiles: number[],
): string => {
  const numYears = scenario.numYears
  const plotW = W - MARGIN.left - MARGIN.right
  const plotH = H - MARGIN.top - MARGIN.bottom
  const x = (yearIndex: number) => MARGIN.left + (yearIndex / (numYears - 1)) * plotW
  const y = (value: number) => MARGIN.top + plotH - (value / yMaxShared) * plotH

  const byPct = new Map(scenario.balanceYearly.map((s) => [s.percentile, s.data]))
  const band = (loP: number, hiP: number, opacity: number): string => {
    const lo = byPct.get(loP)
    const hi = byPct.get(hiP)
    if (!lo || !hi) return ''
    const top = hi.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('')
    const bottom = lo
      .map((v, i) => `L${x(lo.length - 1 - i).toFixed(1)},${y(lo[lo.length - 1 - i] ?? 0).toFixed(1)}`)
      .join('')
    return `<path d="${top}${bottom}Z" class="band" style="opacity:${opacity}"/>`
  }
  const sorted = [...percentiles].sort((a, b) => a - b)
  const outer = band(sorted[0] ?? 5, sorted[sorted.length - 1] ?? 95, 0.1)
  const inner =
    sorted.length >= 4 ? band(sorted[1] ?? 25, sorted[sorted.length - 2] ?? 75, 0.16) : ''
  const medianData = byPct.get(50) ?? scenario.balanceYearly[0]?.data ?? []
  const median = medianData
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join('')

  const yTicks = _niceTicks(yMaxShared)
  const grid = yTicks
    .map(
      (v) =>
        `<line x1="${MARGIN.left}" x2="${W - MARGIN.right}" y1="${y(v)}" y2="${y(v)}" class="grid"/>` +
        `<text x="${MARGIN.left - 8}" y="${y(v) + 4}" class="tick" text-anchor="end">${_usdCompact(v)}</text>`,
    )
    .join('')
  const xTickEvery = numYears > 60 ? 20 : numYears > 30 ? 10 : 5
  const xAxis =
    _.range(0, numYears, xTickEvery)
      .map(
        (yi) =>
          `<text x="${x(yi)}" y="${H - 10}" class="tick" text-anchor="middle">${scenario.anchorYear + yi}</text>`,
      )
      .join('') +
    `<line x1="${MARGIN.left}" x2="${W - MARGIN.right}" y1="${MARGIN.top + plotH}" y2="${MARGIN.top + plotH}" class="axis"/>`
  const ws = scenario.withdrawalStartYearIndex
  const marker =
    ws > 0 && ws < numYears
      ? `<line x1="${x(ws)}" x2="${x(ws)}" y1="${MARGIN.top}" y2="${MARGIN.top + plotH}" class="marker"/>`
      : ''

  const bandLabel = `p${sorted[0] ?? 5}–p${sorted[sorted.length - 1] ?? 95} band`
  const chartData = _esc(
    JSON.stringify({
      anchorYear: scenario.anchorYear,
      ageAtYear0: scenario.person1AgeAtYear0,
      numYears,
      yMax: yMaxShared,
      margin: MARGIN,
      w: W,
      h: H,
      series: scenario.balanceYearly.map((s) => ({
        label: `p${s.percentile}`,
        color: 0,
        data: s.data,
      })),
    }),
  )
  return (
    `<figure class="fan"><figcaption>${_esc(scenario.name)} <span class="muted">(${bandLabel}, median line)</span></figcaption>` +
    `<div class="chart-wrap"><svg viewBox="0 0 ${W} ${H}" class="pc-chart" role="img" aria-label="Portfolio balance percentiles: ${_esc(scenario.name)}" data-chart="${chartData}">` +
    grid +
    xAxis +
    marker +
    outer +
    inner +
    `<path d="${median}" class="line" style="stroke: var(--series-1)"/>` +
    `<line class="crosshair" x1="0" x2="0" y1="${MARGIN.top}" y2="${MARGIN.top + plotH}" style="display:none"/>` +
    `</svg><div class="tooltip" style="display:none"></div></div></figure>`
  )
}

const _timelineSvg = (scenario: ScenarioCompare, colorIndex: number): string => {
  const events = scenario.events
  if (events.length === 0) return ''
  const rowH = 22
  const headerH = 22
  const height = headerH + events.length * rowH + 8
  const numYears = scenario.numYears
  const left = 230
  const plotW = W - left - 24
  const x = (mfn: number) => left + (mfn / (numYears * 12)) * plotW
  const rows = events
    .map((event, i) => {
      const yMid = headerH + i * rowH + rowH / 2
      const x1 = x(event.mfnStart)
      const x2 = Math.max(x(event.mfnEnd + 1), x1 + 4)
      const title = `${event.label}: ${
        event.isOneTime
          ? _usd(event.perMonthAmount) + ' one-time'
          : _usd(event.perMonthAmount) +
            '/mo' +
            (event.annualGrowthPercent !== null
              ? ` growing ${event.annualGrowthPercent}%/yr`
              : '')
      }`
      return (
        `<text x="${left - 10}" y="${yMid + 4}" class="tick" text-anchor="end">${_esc(_.truncate(event.label, { length: 32 }))}</text>` +
        `<rect x="${x1.toFixed(1)}" y="${yMid - 5}" width="${(x2 - x1).toFixed(1)}" height="10" rx="4" class="evt evt-${event.kind}"><title>${_esc(title)}</title></rect>`
      )
    })
    .join('')
  const decadeTicks = _.range(0, numYears, 10)
    .map(
      (yi) =>
        `<text x="${x(yi * 12)}" y="${headerH - 8}" class="tick" text-anchor="middle">${scenario.anchorYear + yi}</text>`,
    )
    .join('')
  return (
    `<figure class="timeline"><figcaption>${_esc(scenario.name)}</figcaption>` +
    `<svg viewBox="0 0 ${W} ${height}" role="img" aria-label="Event timeline: ${_esc(scenario.name)}">${decadeTicks}${rows}</svg></figure>`
  )
}

const _comparisonTable = (data: CompareData): string => {
  const base =
    data.baseSlug !== null
      ? data.scenarios.find((x) => x.slug === data.baseSlug) ?? null
      : null
  const delta = (value: number, baseValue: number | null, fmt: (x: number) => string) => {
    if (baseValue === null || baseValue === value) return ''
    const diff = value - baseValue
    const sign = diff > 0 ? '+' : '−'
    return ` <span class="delta">(${sign}${fmt(Math.abs(diff))})</span>`
  }
  const rows = data.scenarios
    .map((s, i) => {
      const isBase = base !== null && s.slug === base.slug
      const b = isBase ? null : base
      const ending = new Map(s.endingBalanceByPercentile.map((x) => [x.percentile, x.balance]))
      const bEnding = b ? new Map(b.endingBalanceByPercentile.map((x) => [x.percentile, x.balance])) : null
      const p = (n: number) => ending.get(n) ?? 0
      return (
        `<tr><td><span class="key" style="background: var(--series-${(i % 8) + 1})"></span>${_esc(s.name)}${isBase ? ' <span class="muted">(base)</span>' : ''}</td>` +
        `<td>${_pct(s.successProbability)}</td>` +
        `<td>${_usd(s.medianBalanceAtRetirement)}${delta(s.medianBalanceAtRetirement, b?.medianBalanceAtRetirement ?? null, _usdCompact)}</td>` +
        `<td>${_usd(s.medianMonthlySpendingAtRetirement)}${delta(s.medianMonthlySpendingAtRetirement, b?.medianMonthlySpendingAtRetirement ?? null, _usd)}</td>` +
        `<td>${_usdCompact(p(5))}${delta(p(5), bEnding?.get(5) ?? null, _usdCompact)}</td>` +
        `<td>${_usdCompact(p(95))}${delta(p(95), bEnding?.get(95) ?? null, _usdCompact)}</td>` +
        `<td class="muted">${s.numRuns}${s.fromCache ? ' (cached)' : ''}</td></tr>`
      )
    })
    .join('')
  return (
    '<table><thead><tr><th>Scenario</th><th>Success</th><th>Median balance at retirement</th>' +
    '<th>Median retirement spending /mo</th><th>Ending p5</th><th>Ending p95</th><th>Runs</th></tr></thead>' +
    `<tbody>${rows}</tbody></table>`
  )
}

const _netFlowTable = (data: CompareData): string => {
  const years = _.uniq(
    data.scenarios.flatMap((s) => s.yearRows.filter((r) => r.netFlow !== 0).map((r) => r.calendarYear)),
  ).sort()
  if (years.length === 0) return ''
  const header =
    '<tr><th>Year</th>' +
    data.scenarios.map((s) => `<th>${_esc(s.name)}</th>`).join('') +
    '</tr>'
  const rows = years
    .map((year) => {
      const cells = data.scenarios
        .map((s) => {
          const row = s.yearRows.find((r) => r.calendarYear === year)
          return `<td>${row && row.netFlow !== 0 ? _usd(row.netFlow) : ''}</td>`
        })
        .join('')
      return `<tr><td>${year}</td>${cells}</tr>`
    })
    .join('')
  return `<details><summary>Net cash flow to portfolio, by year</summary><table class="num"><thead>${header}</thead><tbody>${rows}</tbody></table></details>`
}

const _dataTable = (id: string, series: ChartSeries[], anchorYear: number): string => {
  const numYears = Math.max(...series.map((s) => s.data.length))
  const step = numYears > 40 ? 5 : 1
  const header =
    '<tr><th>Year</th>' + series.map((s) => `<th>${_esc(s.label)}</th>`).join('') + '</tr>'
  const rows = _.range(0, numYears, step)
    .map(
      (yi) =>
        `<tr><td>${anchorYear + yi}</td>` +
        series.map((s) => `<td>${_usd(s.data[yi] ?? 0)}</td>`).join('') +
        '</tr>',
    )
    .join('')
  return `<details><summary>Data table</summary><table class="num"><thead>${header}</thead><tbody>${rows}</tbody></table></details>`
}

const TOOLTIP_SCRIPT = `
document.querySelectorAll('svg.pc-chart').forEach((svg) => {
  const cfg = JSON.parse(svg.getAttribute('data-chart'))
  const wrap = svg.parentElement
  const tooltip = wrap.querySelector('.tooltip')
  const crosshair = svg.querySelector('.crosshair')
  const plotW = cfg.w - cfg.margin.left - cfg.margin.right
  const fmt = (x) => '$' + Math.round(x).toLocaleString('en-US')
  svg.addEventListener('mousemove', (e) => {
    const rect = svg.getBoundingClientRect()
    const sx = ((e.clientX - rect.left) / rect.width) * cfg.w
    const t = (sx - cfg.margin.left) / plotW
    if (t < 0 || t > 1) { tooltip.style.display = 'none'; crosshair.style.display = 'none'; return }
    const yi = Math.round(t * (cfg.numYears - 1))
    const cx = cfg.margin.left + (yi / (cfg.numYears - 1)) * plotW
    crosshair.setAttribute('x1', cx); crosshair.setAttribute('x2', cx)
    crosshair.style.display = ''
    const lines = cfg.series.map((s) =>
      '<span class="row"><span class="key" style="background: var(--series-' + (s.color + 1) + ')"></span>' +
      s.label + ': ' + fmt(s.data[Math.min(yi, s.data.length - 1)] || 0) + '</span>').join('')
    tooltip.innerHTML = '<strong>' + (cfg.anchorYear + yi) + '</strong> (age ' + (cfg.ageAtYear0 + yi) + ')<br>' + lines
    tooltip.style.display = 'block'
    const wrapRect = wrap.getBoundingClientRect()
    let left = e.clientX - wrapRect.left + 14
    if (left + tooltip.offsetWidth > wrapRect.width) left = left - tooltip.offsetWidth - 28
    tooltip.style.left = left + 'px'
    tooltip.style.top = (e.clientY - wrapRect.top + 10) + 'px'
  })
  svg.addEventListener('mouseleave', () => {
    tooltip.style.display = 'none'; crosshair.style.display = 'none'
  })
})
`

export const STYLE = `
:root {
  color-scheme: light;
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  ${CATEGORICAL_LIGHT.map((c, i) => `--series-${i + 1}: ${c};`).join(' ')}
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    ${CATEGORICAL_DARK.map((c, i) => `--series-${i + 1}: ${c};`).join(' ')}
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-1: #1a1a19; --page: #0d0d0d;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  ${CATEGORICAL_DARK.map((c, i) => `--series-${i + 1}: ${c};`).join(' ')}
}
* { box-sizing: border-box }
body {
  margin: 0; background: var(--page); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 960px; margin: 0 auto; padding: 32px 24px 64px }
h1 { font-size: 24px; margin: 0 0 4px }
h2 { font-size: 17px; margin: 36px 0 12px }
.sub { color: var(--text-secondary); margin: 0 0 24px }
.muted { color: var(--muted); font-weight: normal }
section.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; margin: 16px 0 }
table { border-collapse: collapse; width: 100%; font-size: 14px }
th { text-align: left; color: var(--text-secondary); font-weight: 600; padding: 6px 10px; border-bottom: 1px solid var(--axis) }
td { padding: 6px 10px; border-bottom: 1px solid var(--grid) }
table.num td, table.num th { text-align: right; font-variant-numeric: tabular-nums }
table.num td:first-child, table.num th:first-child { text-align: left }
.delta { color: var(--muted); font-size: 12px }
.key { display: inline-block; width: 10px; height: 10px; border-radius: 5px; margin-right: 7px }
.chart-wrap { position: relative }
svg { display: block; width: 100%; height: auto }
svg .grid { stroke: var(--grid); stroke-width: 1 }
svg .axis { stroke: var(--axis); stroke-width: 1 }
svg .marker { stroke: var(--axis); stroke-width: 1; stroke-dasharray: none }
svg .tick { fill: var(--muted); font-size: 11px; font-family: inherit; font-variant-numeric: tabular-nums }
svg .endlabel { fill: var(--text-secondary); font-size: 12px; font-family: inherit }
svg .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round }
svg .band { fill: var(--series-1) }
svg .crosshair { stroke: var(--axis); stroke-width: 1 }
svg .ring { stroke: var(--surface-1); stroke-width: 2 }
svg .evt { fill: var(--series-1) }
svg .evt-retirementIncome { fill: var(--series-3) }
svg .evt-expenseEssential { fill: var(--series-2) }
svg .evt-expenseDiscretionary { fill: var(--series-5) }
.tooltip {
  position: absolute; pointer-events: none; background: var(--surface-1);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px;
  font-size: 12.5px; color: var(--text-primary); box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  max-width: 280px; z-index: 2;
}
.tooltip .row { display: block; font-variant-numeric: tabular-nums }
figure { margin: 18px 0 }
figcaption { font-size: 14px; font-weight: 600; margin-bottom: 6px }
details { margin: 10px 0 }
summary { cursor: pointer; color: var(--text-secondary); font-size: 13.5px }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--text-secondary); margin: 6px 0 2px }
.legend span { display: inline-flex; align-items: center }
`

export const getComparisonHtml = (data: CompareData, meta: { generatedNote: string }): string => {
  if (data.scenarios.length > 8)
    throw new ScenarioError(
      `Comparison report supports at most 8 scenarios (got ${data.scenarios.length}); ` +
        'split the comparison or drop scenarios.',
    )
  const anchorYear = data.scenarios[0]?.anchorYear ?? new Date().getFullYear()
  const ageAtYear0 = data.scenarios[0]?.person1AgeAtYear0 ?? 0
  const medianBalanceSeries: ChartSeries[] = data.scenarios.map((s, i) => ({
    label: s.name,
    color: i % 8,
    data: (s.balanceYearly.find((x) => x.percentile === 50) ?? s.balanceYearly[0])?.data ?? [],
  }))
  const medianSpendingSeries: ChartSeries[] = data.scenarios.map((s, i) => ({
    label: s.name,
    color: i % 8,
    data: (s.spendingYearly.find((x) => x.percentile === 50) ?? s.spendingYearly[0])?.data ?? [],
  }))
  const withdrawalStart = data.scenarios[0]?.withdrawalStartYearIndex ?? null
  const sameRetirement = data.scenarios.every(
    (s) => s.withdrawalStartYearIndex === withdrawalStart,
  )
  const fanYMax = _niceMax(
    Math.max(1, ...data.scenarios.flatMap((s) => s.balanceYearly.flatMap((p) => p.data))),
  )
  const legend =
    data.scenarios.length >= 2
      ? `<div class="legend">${data.scenarios
          .map(
            (s, i) =>
              `<span><span class="key" style="background: var(--series-${(i % 8) + 1})"></span>${_esc(s.name)}</span>`,
          )
          .join('')}</div>`
      : ''

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scenario comparison</title>
<style>${STYLE}</style></head><body><main>
<h1>Scenario comparison</h1>
<p class="sub">${_esc(meta.generatedNote)}</p>

<section class="card">
<h2 style="margin-top:0">Outcomes</h2>
${_comparisonTable(data)}
<p class="muted" style="font-size:12.5px">Median retirement spending is the average monthly total spending over the first year of retirement at the 50th percentile. TPAW amortizes wealth, so ending balances near zero are by design when no legacy target is set.</p>
</section>

<section class="card">
<h2 style="margin-top:0">Median portfolio balance</h2>
${legend}
${_lineChartSvg('balance-overlay', medianBalanceSeries, anchorYear, ageAtYear0, sameRetirement ? withdrawalStart : null, 'Median portfolio balance by year')}
${_dataTable('balance-table', medianBalanceSeries, anchorYear)}
</section>

<section class="card">
<h2 style="margin-top:0">Median monthly spending</h2>
${legend}
${_lineChartSvg('spending-overlay', medianSpendingSeries, anchorYear, ageAtYear0, sameRetirement ? withdrawalStart : null, 'Median monthly spending by year')}
${_dataTable('spending-table', medianSpendingSeries, anchorYear)}
</section>

<section class="card">
<h2 style="margin-top:0">Balance uncertainty per scenario</h2>
${data.scenarios.map((s) => _fanChartSvg(s, fanYMax, data.percentiles)).join('')}
</section>

<section class="card">
<h2 style="margin-top:0">Events</h2>
<div class="legend"><span><span class="key" style="background: var(--series-1)"></span>savings</span><span><span class="key" style="background: var(--series-3)"></span>retirement income</span><span><span class="key" style="background: var(--series-2)"></span>essential expense</span><span><span class="key" style="background: var(--series-5)"></span>discretionary expense</span></div>
${data.scenarios.map((s, i) => _timelineSvg(s, i)).join('')}
${_netFlowTable(data)}
</section>

</main><script>${TOOLTIP_SCRIPT}</script></body></html>`
  return html
}
