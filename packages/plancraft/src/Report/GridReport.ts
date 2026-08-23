import _ from 'lodash'
import { ScenarioRun } from '../Batch/RunMatrix'
import { GeneratedGrid } from '../Grid/GenerateGrid'
import { STYLE, _esc, _pct, _usd, _usdCompact } from './HtmlReport'

// Grid report: for full-factorial sweeps too large for the overlay
// comparison. Ranked outcomes, per-decision main effects (bars), and
// heatmaps for the two highest-impact dimension pairs. Sequential blue ramp
// from the dataviz reference palette; no external dependencies.

const SEQ_RAMP = [
  '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6',
  '#256abf', '#1c5cab', '#184f95', '#104281',
] // steps 150..650: both ends keep label contrast on light and dark surfaces.

export type GridComboResult = {
  cells: Record<string, string>
  cellNames: Record<string, string>
  name: string
  successProbability: number
  medianRetirementSpending: number
  medianBalanceAtRetirement: number
  endingBalanceP50: number
}

export type GridReportData = {
  gridName: string
  gridDescription: string | null
  dimensions: { id: string; name: string; variantNames: Record<string, string> }[]
  combos: GridComboResult[]
  mainEffects: {
    dimensionId: string
    dimensionName: string
    variants: { id: string; name: string; meanSpending: number; delta: number }[]
    spread: number
  }[]
}

const _medianSeries = <T extends { percentile: number; data: number[] }>(
  series: T[],
): number[] =>
  (series.find((x) => x.percentile === 50) ?? series[Math.floor(series.length / 2)])
    ?.data ?? []

export const getGridReportData = (
  generated: GeneratedGrid,
  runs: ScenarioRun[],
): GridReportData => {
  const combos: GridComboResult[] = generated.combos.map((combo, i) => {
    const run = runs[i]!
    const { compiled, outcome } = run
    const wsMFN = compiled.withdrawalStartMFN
    const spending = _medianSeries(outcome.withdrawalsTotal)
    const balance = _medianSeries(outcome.balanceStart)
    return {
      cells: combo.cells,
      cellNames: combo.cellNames,
      name: combo.name,
      successProbability: outcome.successProbability,
      medianRetirementSpending: _.mean(spending.slice(wsMFN, wsMFN + 12)) || 0,
      medianBalanceAtRetirement: balance[Math.min(wsMFN, balance.length - 1)] ?? 0,
      endingBalanceP50:
        outcome.endingBalanceByPercentile.find((x) => x.percentile === 50)
          ?.balance ?? 0,
    }
  })

  const mainEffects = generated.grid.dimensions.map((dimension) => {
    const variants = dimension.variants.map((variant) => {
      const matching = combos.filter((c) => c.cells[dimension.id] === variant.id)
      return {
        id: variant.id,
        name: variant.name,
        meanSpending: _.mean(matching.map((c) => c.medianRetirementSpending)) || 0,
        delta: 0,
      }
    })
    const first = variants[0]!.meanSpending
    for (const v of variants) v.delta = v.meanSpending - first
    return {
      dimensionId: dimension.id,
      dimensionName: dimension.name,
      variants,
      spread:
        Math.max(...variants.map((v) => v.meanSpending)) -
        Math.min(...variants.map((v) => v.meanSpending)),
    }
  })

  return {
    gridName: generated.grid.name,
    gridDescription: generated.grid.description ?? null,
    dimensions: generated.grid.dimensions.map((d) => ({
      id: d.id,
      name: d.name,
      variantNames: Object.fromEntries(d.variants.map((v) => [v.id, v.name])),
    })),
    combos,
    mainEffects,
  }
}

export const getGridCsv = (data: GridReportData): string => {
  const dims = data.dimensions
  const header = [
    ...dims.map((d) => d.id),
    'medianRetirementSpendingPerMonth',
    'successProbability',
    'medianBalanceAtRetirement',
    'endingBalanceP50',
  ].join(',')
  const rows = data.combos.map((c) =>
    [
      ...dims.map((d) => c.cells[d.id]),
      Math.round(c.medianRetirementSpending),
      c.successProbability.toFixed(4),
      Math.round(c.medianBalanceAtRetirement),
      Math.round(c.endingBalanceP50),
    ].join(','),
  )
  return [header, ...rows].join('\n') + '\n'
}

const _inkForFill = (hex: string): string => {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return luminance > 150 ? '#0b0b0b' : '#ffffff'
}

const _mainEffectsSection = (data: GridReportData): string => {
  const max = Math.max(
    1,
    ...data.mainEffects.flatMap((e) => e.variants.map((v) => v.meanSpending)),
  )
  const groups = _.orderBy(data.mainEffects, (e) => -e.spread)
    .map((effect) => {
      const rows = effect.variants
        .map((v) => {
          const width = Math.max(2, (v.meanSpending / max) * 420)
          const deltaText =
            v.delta === 0
              ? ''
              : ` <span class="delta">(${v.delta > 0 ? '+' : '−'}${_usd(Math.abs(v.delta))})</span>`
          return (
            `<div class="me-row"><span class="me-label">${_esc(v.name)}</span>` +
            `<svg width="${Math.ceil(width) + 90}" height="22" class="me-bar" role="img" aria-label="${_esc(v.name)}: ${_usd(v.meanSpending)}">` +
            `<rect x="0" y="2" width="${width.toFixed(1)}" height="18" rx="0" style="fill: var(--series-1)"/>` +
            `<rect x="${Math.max(0, width - 4).toFixed(1)}" y="2" width="4" height="18" rx="2" style="fill: var(--series-1)"/>` +
            `<text x="${(width + 8).toFixed(1)}" y="16" class="me-value">${_usd(v.meanSpending)}</text>` +
            `</svg>${deltaText}</div>`
          )
        })
        .join('')
      return (
        `<div class="me-group"><h3>${_esc(effect.dimensionName)}` +
        ` <span class="muted">(impact range ${_usd(effect.spread)}/mo)</span></h3>${rows}</div>`
      )
    })
    .join('')
  return (
    `<section class="card"><h2 style="margin-top:0">What each decision is worth</h2>` +
    `<p class="muted" style="font-size:13px">Mean of median first-year retirement spending, averaged across all other decisions. Deltas vs the first variant.</p>` +
    groups +
    `</section>`
  )
}

const _heatmap = (
  data: GridReportData,
  rowDimId: string,
  colDimId: string,
): string => {
  const rowDim = data.dimensions.find((d) => d.id === rowDimId)!
  const colDim = data.dimensions.find((d) => d.id === colDimId)!
  const rowIds = Object.keys(rowDim.variantNames)
  const colIds = Object.keys(colDim.variantNames)
  const cells = rowIds.map((r) =>
    colIds.map((c) => {
      const matching = data.combos.filter(
        (x) => x.cells[rowDimId] === r && x.cells[colDimId] === c,
      )
      return _.mean(matching.map((x) => x.medianRetirementSpending)) || 0
    }),
  )
  const flat = cells.flat()
  const min = Math.min(...flat)
  const max = Math.max(...flat)
  const fill = (v: number) => {
    const t = max === min ? 0.5 : (v - min) / (max - min)
    return SEQ_RAMP[Math.min(SEQ_RAMP.length - 1, Math.floor(t * SEQ_RAMP.length))]!
  }
  const cellW = 118, cellH = 44, left = 215, top = 60
  const width = left + colIds.length * cellW + 10
  const height = top + rowIds.length * cellH + 10
  const colHeaders = colIds
    .map(
      (c, j) =>
        `<text x="${left + j * cellW + cellW / 2}" y="${top - 10}" class="tick" text-anchor="middle">${_esc(colDim.variantNames[c]!)}</text>`,
    )
    .join('')
  const body = rowIds
    .map((r, i) => {
      const rowLabel = `<text x="${left - 10}" y="${top + i * cellH + cellH / 2 + 4}" class="tick" text-anchor="end">${_esc(rowDim.variantNames[r]!)}</text>`
      const rowCells = colIds
        .map((c, j) => {
          const v = cells[i]![j]!
          const f = fill(v)
          return (
            `<rect x="${left + j * cellW + 1}" y="${top + i * cellH + 1}" width="${cellW - 2}" height="${cellH - 2}" rx="4" fill="${f}">` +
            `<title>${_esc(rowDim.variantNames[r]!)} × ${_esc(colDim.variantNames[c]!)}: ${_usd(v)}/mo (mean over other decisions)</title></rect>` +
            `<text x="${left + j * cellW + cellW / 2}" y="${top + i * cellH + cellH / 2 + 4}" text-anchor="middle" style="fill:${_inkForFill(f)};font-size:12.5px;font-variant-numeric:tabular-nums">${_usdCompact(v)}</text>`
          )
        })
        .join('')
      return rowLabel + rowCells
    })
    .join('')
  return (
    `<figure><figcaption>${_esc(rowDim.name)} × ${_esc(colDim.name)} <span class="muted">(mean median retirement spending /mo; darker = higher; range ${_usd(min)}–${_usd(max)})</span></figcaption>` +
    `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Heatmap: ${_esc(rowDim.name)} by ${_esc(colDim.name)}" style="max-width:${width}px">${colHeaders}${body}</svg></figure>`
  )
}

const _rankedTable = (data: GridReportData, limit: number | null): string => {
  const sorted = _.orderBy(data.combos, (c) => -c.medianRetirementSpending)
  const shown = limit === null ? sorted : sorted.slice(0, limit)
  const dims = data.dimensions
  const header =
    '<tr><th>#</th>' +
    dims.map((d) => `<th>${_esc(d.name)}</th>`).join('') +
    '<th>Spending /mo</th><th>Success</th><th>Balance at retirement</th><th>Ending p50</th></tr>'
  const rows = shown
    .map((c, i) => {
      const rank = sorted.indexOf(c) + 1
      return (
        `<tr><td class="muted">${rank}</td>` +
        dims.map((d) => `<td>${_esc(c.cellNames[d.id] ?? '')}</td>`).join('') +
        `<td>${_usd(c.medianRetirementSpending)}</td>` +
        `<td>${_pct(c.successProbability)}</td>` +
        `<td>${_usdCompact(c.medianBalanceAtRetirement)}</td>` +
        `<td>${_usdCompact(c.endingBalanceP50)}</td></tr>`
      )
    })
    .join('')
  return `<table class="num"><thead>${header}</thead><tbody>${rows}</tbody></table>`
}

export const getGridHtml = (
  data: GridReportData,
  meta: { generatedNote: string },
): string => {
  // Heatmaps pair the dimensions by main-effect spread: biggest two together,
  // then the remaining two (if present).
  const bySpread = _.orderBy(data.mainEffects, (e) => -e.spread).map(
    (e) => e.dimensionId,
  )
  const heatmaps: string[] = []
  if (bySpread.length >= 2) heatmaps.push(_heatmap(data, bySpread[0]!, bySpread[1]!))
  if (bySpread.length >= 4) heatmaps.push(_heatmap(data, bySpread[2]!, bySpread[3]!))

  const best = _.maxBy(data.combos, (c) => c.medianRetirementSpending)!
  const worst = _.minBy(data.combos, (c) => c.medianRetirementSpending)!

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${_esc(data.gridName)}</title>
<style>${STYLE}
.me-group { margin: 14px 0 } .me-group h3 { font-size: 14.5px; margin: 10px 0 6px }
.me-row { display: flex; align-items: center; gap: 10px; margin: 3px 0 }
.me-label { width: 190px; text-align: right; font-size: 13px; color: var(--text-secondary); flex-shrink: 0 }
svg.me-bar { width: auto; height: 22px; flex-shrink: 0 }
.me-value { fill: var(--text-primary); font-size: 12.5px; font-variant-numeric: tabular-nums }
</style></head><body><main>
<h1>${_esc(data.gridName)}</h1>
<p class="sub">${_esc(meta.generatedNote)}</p>
${data.gridDescription ? `<p class="sub">${_esc(data.gridDescription)}</p>` : ''}

<section class="card">
<h2 style="margin-top:0">Range of outcomes</h2>
<p>${data.combos.length} combinations. Median first-year retirement spending spans
<strong>${_usd(worst.medianRetirementSpending)}/mo</strong> (${_esc(worst.name)}) to
<strong>${_usd(best.medianRetirementSpending)}/mo</strong> (${_esc(best.name)}).</p>
</section>

${_mainEffectsSection(data)}

<section class="card">
<h2 style="margin-top:0">Decision interactions</h2>
${heatmaps.join('')}
</section>

<section class="card">
<h2 style="margin-top:0">Top 15 combinations</h2>
${_rankedTable(data, 15)}
<details><summary>All ${data.combos.length} combinations</summary>${_rankedTable(data, null)}</details>
</section>

</main></body></html>`
}
