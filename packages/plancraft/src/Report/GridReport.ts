import { block } from '@tpaw/common'
import _ from 'lodash'
import { ScenarioRun } from '../Batch/RunMatrix'
import { GeneratedGrid } from '../Grid/GenerateGrid'
import { STYLE, _esc, _pct, _usd, _usdCompact } from './HtmlReport'

// Grid report for full-factorial decision sweeps, optionally replicated
// across "conditions" (states of the world such as return assumptions).
// Sections: decision effects with cross-condition stability, interaction
// heatmap (reference condition), ranked combos per condition, CSV export.
// Sequential blue ramp from the dataviz reference palette; no external deps.

const SEQ_RAMP = [
  '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6',
  '#256abf', '#1c5cab', '#184f95', '#104281',
] // steps 150..650: both ends keep label contrast on light and dark surfaces.

export type GridComboResult = {
  conditionId: string
  cells: Record<string, string>
  cellNames: Record<string, string>
  name: string
  successProbability: number
  medianRetirementSpending: number
  medianBalanceAtRetirement: number
  endingBalanceP50: number
  // Annual-resolution median trajectories for the interactive explorer,
  // quantized to keep the embedded payload small: balance in $1,000s,
  // lifestyle spending in $/month. Index 0 is the anchor year.
  balanceByYear: number[]
  spendingByYear: number[]
  // Withdrawal start as a year index into the arrays above. Varies by combo
  // whenever a dimension moves a retirement age.
  retireYear: number
}

export type GridReportData = {
  gridName: string
  gridDescription: string | null
  dimensions: { id: string; name: string; variantNames: Record<string, string> }[]
  conditions: { id: string; name: string }[]
  referenceConditionId: string
  // Timeline for the explorer's x-axis, shared by every combo in the grid.
  // Retirement year is per-combo (see GridComboResult.retireYear), since
  // dimensions may move it.
  timeline: {
    anchorYear: number
    person1AgeAtAnchor: number
    numYears: number
  }
  results: GridComboResult[]
  // dimension -> variant -> condition -> mean spending
  mainEffects: {
    dimensionId: string
    dimensionName: string
    variants: {
      id: string
      name: string
      meanSpendingByCondition: Record<string, number>
    }[]
    // Spread under the reference condition (used for ordering/heatmap pick).
    spread: number
  }[]
  // Spearman rank correlation of combo ordering between condition pairs.
  rankStability: { a: string; b: string; spearman: number }[]
}

const _medianSeries = <T extends { percentile: number; data: number[] }>(
  series: T[],
): number[] =>
  (series.find((x) => x.percentile === 50) ?? series[Math.floor(series.length / 2)])
    ?.data ?? []

const _spearman = (a: number[], b: number[]): number => {
  const rank = (xs: number[]) => {
    const order = _.sortBy(_.range(xs.length), (i) => xs[i])
    const ranks = new Array<number>(xs.length)
    order.forEach((originalIndex, r) => (ranks[originalIndex] = r))
    return ranks
  }
  const ra = rank(a), rb = rank(b)
  const n = a.length
  const d2 = _.sum(_.range(n).map((i) => (ra[i]! - rb[i]!) ** 2))
  return 1 - (6 * d2) / (n * (n * n - 1))
}

export const getGridReportData = (
  generated: GeneratedGrid,
  // runs ordered condition-major: for each condition, all combos in order.
  runs: ScenarioRun[],
): GridReportData => {
  const { combos, conditions } = generated
  const results: GridComboResult[] = runs.map((run, i) => {
    const condition = conditions[Math.floor(i / combos.length)]!
    const combo = combos[i % combos.length]!
    const { compiled, outcome } = run
    const wsMFN = compiled.withdrawalStartMFN
    // General (lifestyle) spending only: totals would count earmarked
    // essential expenses (e.g. tuition still being paid during an early
    // retirement) as spending and invert cost comparisons.
    const spending = _medianSeries(outcome.withdrawalsRegular)
    const balance = _medianSeries(outcome.balanceStart)
    // Sample one point per 12 months (January of each anchor-relative year).
    const byYear = (series: number[], scale: number) =>
      _.range(0, Math.ceil(series.length / 12)).map((y) =>
        Math.round((series[y * 12] ?? 0) * scale),
      )
    return {
      conditionId: condition.id,
      cells: combo.cells,
      cellNames: combo.cellNames,
      name: combo.name,
      successProbability: outcome.successProbability,
      medianRetirementSpending: _.mean(spending.slice(wsMFN, wsMFN + 12)) || 0,
      medianBalanceAtRetirement: balance[Math.min(wsMFN, balance.length - 1)] ?? 0,
      endingBalanceP50:
        outcome.endingBalanceByPercentile.find((x) => x.percentile === 50)
          ?.balance ?? 0,
      balanceByYear: byYear(balance, 1 / 1000),
      spendingByYear: byYear(spending, 1),
      retireYear: Math.floor(wsMFN / 12),
    }
  })

  const referenceConditionId =
    conditions.find((c) => c.id.includes('base'))?.id ??
    conditions[Math.floor((conditions.length - 1) / 2)]!.id

  const mainEffects = generated.grid.dimensions.map((dimension) => {
    const variants = dimension.variants.map((variant) => ({
      id: variant.id,
      name: variant.name,
      meanSpendingByCondition: Object.fromEntries(
        conditions.map((condition) => [
          condition.id,
          _.mean(
            results
              .filter(
                (r) =>
                  r.conditionId === condition.id &&
                  r.cells[dimension.id] === variant.id,
              )
              .map((r) => r.medianRetirementSpending),
          ) || 0,
        ]),
      ),
    }))
    const refMeans = variants.map(
      (v) => v.meanSpendingByCondition[referenceConditionId] ?? 0,
    )
    return {
      dimensionId: dimension.id,
      dimensionName: dimension.name,
      variants,
      spread: Math.max(...refMeans) - Math.min(...refMeans),
    }
  })

  const rankStability: GridReportData['rankStability'] = []
  for (let i = 0; i < conditions.length; i++)
    for (let j = i + 1; j < conditions.length; j++) {
      const spendingOf = (conditionId: string) =>
        combos.map(
          (combo) =>
            results.find(
              (r) => r.conditionId === conditionId && r.name === combo.name,
            )!.medianRetirementSpending,
        )
      rankStability.push({
        a: conditions[i]!.id,
        b: conditions[j]!.id,
        spearman: _spearman(spendingOf(conditions[i]!.id), spendingOf(conditions[j]!.id)),
      })
    }

  return {
    gridName: generated.grid.name,
    gridDescription: generated.grid.description ?? null,
    dimensions: generated.grid.dimensions.map((d) => ({
      id: d.id,
      name: d.name,
      variantNames: Object.fromEntries(d.variants.map((v) => [v.id, v.name])),
    })),
    conditions: conditions.map((c) => ({ id: c.id, name: c.name })),
    referenceConditionId,
    timeline: block(() => {
      const { compiled } = runs[0]!
      return {
        anchorYear: compiled.anchor.year,
        person1AgeAtAnchor: Math.floor(
          compiled.ages.person1.currentAgeMonths / 12,
        ),
        numYears: Math.max(...results.map((r) => r.balanceByYear.length)),
      }
    }),
    results,
    mainEffects,
    rankStability,
  }
}

export const getGridCsv = (data: GridReportData): string => {
  const dims = data.dimensions
  const header = [
    'condition',
    ...dims.map((d) => d.id),
    'medianRetirementSpendingPerMonth',
    'successProbability',
    'medianBalanceAtRetirement',
    'endingBalanceP50',
  ].join(',')
  const rows = data.results.map((r) =>
    [
      r.conditionId,
      ...dims.map((d) => r.cells[d.id]),
      Math.round(r.medianRetirementSpending),
      r.successProbability.toFixed(4),
      Math.round(r.medianBalanceAtRetirement),
      Math.round(r.endingBalanceP50),
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

// Decision effects with stability: per dimension, a table of variants x
// conditions (mean spending, delta vs the dimension's first variant).
const _effectsSection = (data: GridReportData): string => {
  const conditionHeaders = data.conditions
    .map(
      (c) =>
        `<th>${_esc(c.name)}${c.id === data.referenceConditionId ? ' <span class="muted">(ref)</span>' : ''}</th>`,
    )
    .join('')
  const groups = _.orderBy(data.mainEffects, (e) => -e.spread)
    .map((effect) => {
      const first = effect.variants[0]!
      const rows = effect.variants
        .map((v) => {
          const cells = data.conditions
            .map((c) => {
              const mean = v.meanSpendingByCondition[c.id] ?? 0
              const delta = mean - (first.meanSpendingByCondition[c.id] ?? 0)
              const deltaText =
                v.id === first.id
                  ? ''
                  : ` <span class="delta">(${delta >= 0 ? '+' : '−'}${_usdCompact(Math.abs(delta))})</span>`
              return `<td>${_usd(mean)}${deltaText}</td>`
            })
            .join('')
          return `<tr><td>${_esc(v.name)}</td>${cells}</tr>`
        })
        .join('')
      return (
        `<h3>${_esc(effect.dimensionName)} <span class="muted">(reference impact range ${_usd(effect.spread)}/mo)</span></h3>` +
        `<table class="num"><thead><tr><th></th>${conditionHeaders}</tr></thead><tbody>${rows}</tbody></table>`
      )
    })
    .join('')
  const stability = data.rankStability
    .map((s) => {
      const nameOf = (id: string) =>
        data.conditions.find((c) => c.id === id)?.name ?? id
      return `${_esc(nameOf(s.a))} ↔ ${_esc(nameOf(s.b))}: ρ = ${s.spearman.toFixed(3)}`
    })
    .join(' &nbsp;·&nbsp; ')
  return (
    `<section class="card"><h2 style="margin-top:0">What each decision is worth, by condition</h2>` +
    `<p class="muted" style="font-size:13px">Mean of median first-year general (lifestyle) retirement spending per month — earmarked essential expenses such as tuition are excluded. Averaged across all other decisions; deltas vs the dimension's first variant.</p>` +
    groups +
    (data.conditions.length > 1
      ? `<p class="muted" style="font-size:13px">Combination ranking stability (Spearman rank correlation of all combos between conditions): ${stability}. Values near 1 mean the decision ordering does not depend on the condition.</p>`
      : '') +
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
  const referenceResults = data.results.filter(
    (r) => r.conditionId === data.referenceConditionId,
  )
  const cells = rowIds.map((r) =>
    colIds.map((c) => {
      const matching = referenceResults.filter(
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
  const cellW = 96, cellH = 40, left = 215, top = 60
  const width = left + colIds.length * cellW + 10
  const height = top + rowIds.length * cellH + 10
  const colHeaders = colIds
    .map(
      (c, j) =>
        `<text x="${left + j * cellW + cellW / 2}" y="${top - 10}" class="tick" text-anchor="middle">${_esc(_.truncate(colDim.variantNames[c]!, { length: 14 }))}</text>`,
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
            `<title>${_esc(rowDim.variantNames[r]!)} × ${_esc(colDim.variantNames[c]!)}: ${_usd(v)}/mo (mean over other decisions, reference condition)</title></rect>` +
            `<text x="${left + j * cellW + cellW / 2}" y="${top + i * cellH + cellH / 2 + 4}" text-anchor="middle" style="fill:${_inkForFill(f)};font-size:12px;font-variant-numeric:tabular-nums">${_usdCompact(v)}</text>`
          )
        })
        .join('')
      return rowLabel + rowCells
    })
    .join('')
  return (
    `<figure><figcaption>${_esc(rowDim.name)} × ${_esc(colDim.name)} <span class="muted">(reference condition; mean median retirement spending /mo; darker = higher; range ${_usd(min)}–${_usd(max)})</span></figcaption>` +
    `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Heatmap: ${_esc(rowDim.name)} by ${_esc(colDim.name)}" style="max-width:${width}px">${colHeaders}${body}</svg></figure>`
  )
}

const _rankedTable = (
  data: GridReportData,
  conditionId: string,
  limit: number | null,
): string => {
  const sorted = _.orderBy(
    data.results.filter((r) => r.conditionId === conditionId),
    (r) => -r.medianRetirementSpending,
  )
  const shown = limit === null ? sorted : sorted.slice(0, limit)
  const dims = data.dimensions
  const header =
    '<tr><th>#</th>' +
    dims.map((d) => `<th>${_esc(d.name)}</th>`).join('') +
    '<th>Spending /mo</th><th>Success</th><th>Balance at retirement</th><th>Ending p50</th></tr>'
  const rows = shown
    .map((r) => {
      const rank = sorted.indexOf(r) + 1
      return (
        `<tr><td class="muted">${rank}</td>` +
        dims.map((d) => `<td>${_esc(r.cellNames[d.id] ?? '')}</td>`).join('') +
        `<td>${_usd(r.medianRetirementSpending)}</td>` +
        `<td>${_pct(r.successProbability)}</td>` +
        `<td>${_usdCompact(r.medianBalanceAtRetirement)}</td>` +
        `<td>${_usdCompact(r.endingBalanceP50)}</td></tr>`
      )
    })
    .join('')
  return `<table class="num"><thead>${header}</thead><tbody>${rows}</tbody></table>`
}

export const getGridHtml = (
  data: GridReportData,
  meta: { generatedNote: string },
): string => {
  const bySpread = _.orderBy(data.mainEffects, (e) => -e.spread).map(
    (e) => e.dimensionId,
  )
  const heatmaps: string[] = []
  if (bySpread.length >= 2) heatmaps.push(_heatmap(data, bySpread[0]!, bySpread[1]!))
  if (bySpread.length >= 4) heatmaps.push(_heatmap(data, bySpread[2]!, bySpread[3]!))

  const referenceResults = data.results.filter(
    (r) => r.conditionId === data.referenceConditionId,
  )
  const best = _.maxBy(referenceResults, (r) => r.medianRetirementSpending)!
  const worst = _.minBy(referenceResults, (r) => r.medianRetirementSpending)!
  const referenceName =
    data.conditions.find((c) => c.id === data.referenceConditionId)?.name ?? ''

  const rankedSections = data.conditions
    .map((condition) => {
      const open = condition.id === data.referenceConditionId
      return (
        `<details${open ? ' open' : ''}><summary><strong>${_esc(condition.name)}</strong> — top 10 of ${
          data.results.filter((r) => r.conditionId === condition.id).length
        } combinations</summary>` +
        _rankedTable(data, condition.id, 10) +
        `<details><summary>All combinations (${_esc(condition.name)})</summary>${_rankedTable(data, condition.id, null)}</details>` +
        `</details>`
      )
    })
    .join('')

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${_esc(data.gridName)}</title>
<style>${STYLE}
h3 { font-size: 14.5px; margin: 18px 0 6px }
table.num td:first-child { white-space: nowrap }
</style></head><body><main>
<h1>${_esc(data.gridName)}</h1>
<p class="sub">${_esc(meta.generatedNote)}</p>
${data.gridDescription ? `<p class="sub">${_esc(data.gridDescription)}</p>` : ''}

<section class="card">
<h2 style="margin-top:0">Range of outcomes <span class="muted">(${_esc(referenceName)})</span></h2>
<p>Median first-year retirement spending spans <strong>${_usd(worst.medianRetirementSpending)}/mo</strong>
(${_esc(worst.name)}) to <strong>${_usd(best.medianRetirementSpending)}/mo</strong> (${_esc(best.name)}).</p>
</section>

${_effectsSection(data)}

<section class="card">
<h2 style="margin-top:0">Decision interactions</h2>
${heatmaps.join('')}
</section>

<section class="card">
<h2 style="margin-top:0">Ranked combinations</h2>
${rankedSections}
</section>

</main></body></html>`
}
