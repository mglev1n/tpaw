import _ from 'lodash'
import { ScenarioRun } from '../Batch/RunMatrix'
import { getYearRows, YearRow } from '../Compile/CompilationReport'
import { EventSchedule } from '../Compile/CompileToPlanParams'

// Everything the comparison report renders, downsampled to yearly points so
// the HTML stays small (monthly arrays run to ~1,200 points per series).

export type YearlySeries = {
  percentile: number
  // One point per year index (0 = now), sampled at January of each year.
  data: number[]
}

export type ScenarioCompare = {
  name: string
  slug: string
  description: string | null
  numRuns: number
  fromCache: boolean
  successProbability: number
  withdrawalStartYearIndex: number
  numYears: number
  person1AgeAtYear0: number
  anchorYear: number
  medianBalanceAtRetirement: number
  // Average monthly total spending over the first year of retirement, at the
  // median percentile - the "what retirement does this buy" number for TPAW.
  medianMonthlySpendingAtRetirement: number
  endingBalanceByPercentile: { percentile: number; balance: number }[]
  balanceYearly: YearlySeries[]
  spendingYearly: YearlySeries[]
  yearRows: YearRow[]
  events: EventSchedule[]
}

export type CompareData = {
  scenarios: ScenarioCompare[]
  percentiles: number[]
  baseSlug: string | null
  maxYears: number
}

const _toYearly = (
  series: { percentile: number; data: number[] }[],
): YearlySeries[] =>
  series.map(({ percentile, data }) => ({
    percentile,
    data: _.range(Math.ceil(data.length / 12)).map((y) => data[y * 12] ?? 0),
  }))

export const getCompareData = (
  runs: ScenarioRun[],
  opts: { baseSlug?: string | null } = {},
): CompareData => {
  const percentiles = runs[0]?.outcome.percentiles ?? []
  const scenarios = runs.map(({ compiled, outcome, fromCache }): ScenarioCompare => {
    const slugify = (x: string) =>
      x
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
    const median = outcome.balanceStart.find((x) => x.percentile === 50) ??
      outcome.balanceStart[Math.floor(outcome.balanceStart.length / 2)]
    // General (lifestyle) spending; totals would include earmarked essential
    // expenses that overlap the start of retirement.
    const medianSpending =
      outcome.withdrawalsRegular.find((x) => x.percentile === 50) ??
      outcome.withdrawalsRegular[Math.floor(outcome.withdrawalsRegular.length / 2)]
    const wsMFN = compiled.withdrawalStartMFN
    const spendingFirstYear = medianSpending
      ? medianSpending.data.slice(wsMFN, wsMFN + 12)
      : []
    return {
      name: compiled.scenario.meta.name,
      slug: slugify(compiled.scenario.meta.name),
      description: compiled.scenario.meta.description ?? null,
      numRuns: outcome.numRuns,
      fromCache,
      successProbability: outcome.successProbability,
      withdrawalStartYearIndex: Math.floor(wsMFN / 12),
      numYears: Math.ceil(outcome.numMonths / 12),
      person1AgeAtYear0: Math.floor(compiled.ages.person1.currentAgeMonths / 12),
      anchorYear: compiled.anchor.year,
      medianBalanceAtRetirement: median?.data[Math.min(wsMFN, (median?.data.length ?? 1) - 1)] ?? 0,
      medianMonthlySpendingAtRetirement:
        spendingFirstYear.length > 0 ? _.mean(spendingFirstYear) : 0,
      endingBalanceByPercentile: outcome.endingBalanceByPercentile,
      balanceYearly: _toYearly(outcome.balanceStart),
      spendingYearly: _toYearly(outcome.withdrawalsTotal),
      yearRows: getYearRows(compiled),
      events: compiled.schedules,
    }
  })
  return {
    scenarios,
    percentiles,
    baseSlug: opts.baseSlug ?? null,
    maxYears: Math.max(0, ...scenarios.map((x) => x.numYears)),
  }
}
