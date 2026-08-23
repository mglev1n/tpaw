import _ from 'lodash'
import { scenarioFileSchema } from '../Schema/ScenarioSchema'
import { compileScenario } from '../Compile/CompileToPlanParams'
import { SimulationOutcome } from '../Engine/SimulateClient'
import { getCompareData } from './CompareData'
import { getComparisonHtml } from './HtmlReport'
import { ScenarioRun } from '../Batch/RunMatrix'

const NOW = 1755950400000

const scenario = scenarioFileSchema.parse({
  plancraft: 1,
  meta: { name: 'Compare test', anchorYear: 2026 },
  household: {
    person1: { currentAge: { years: 40 }, retirementAge: { years: 60 }, maxAge: { years: 90 } },
  },
  portfolio: { balance: 500000 },
  events: [
    {
      id: 'save',
      kind: 'savings',
      amount: { perMonth: 5000 },
      timing: { from: { named: 'now' }, to: { named: 'lastWorkingMonth' } },
    },
  ],
})

const syntheticOutcome = (numMonths: number): SimulationOutcome => {
  const percentiles = [5, 50, 95]
  const series = (scale: number) =>
    percentiles.map((percentile, i) => ({
      percentile,
      data: _.range(numMonths).map((mfn) => scale * (i + 1) * (mfn + 1)),
    }))
  return {
    numRuns: 100,
    numRunsWithInsufficientFunds: 3,
    successProbability: 0.97,
    percentiles,
    numMonths,
    balanceStart: series(10),
    withdrawalsEssential: series(0),
    withdrawalsDiscretionary: series(0),
    withdrawalsRegular: series(1),
    withdrawalsTotal: series(1),
    stockAllocationSavingsPortfolio: series(0.001),
    endingBalanceByPercentile: percentiles.map((percentile) => ({
      percentile,
      balance: percentile * 1000,
    })),
    serverPerformance: null,
  }
}

describe('getCompareData', () => {
  const compiled = compileScenario(scenario, { now: NOW })
  const run: ScenarioRun = {
    scenarioPath: '/x/compare-test.json',
    compiled,
    outcome: syntheticOutcome(compiled.norm.ages.simulationMonths.numMonths),
    fromCache: false,
  }

  test('aggregates and downsamples', () => {
    const data = getCompareData([run], { baseSlug: 'compare-test' })
    expect(data.scenarios).toHaveLength(1)
    const s = data.scenarios[0]!
    expect(s.slug).toBe('compare-test')
    expect(s.successProbability).toBe(0.97)
    expect(s.withdrawalStartYearIndex).toBe(20)
    // Yearly downsampling takes January values: year y = monthly[y * 12].
    const p50 = s.balanceYearly.find((x) => x.percentile === 50)!
    expect(p50.data[0]).toBe(10 * 2 * 1)
    expect(p50.data[1]).toBe(10 * 2 * 13)
    // Median monthly spending at retirement start: mean over first 12 months.
    const wsMFN = 240
    expect(s.medianMonthlySpendingAtRetirement).toBeCloseTo(
      _.mean(_.range(wsMFN, wsMFN + 12).map((mfn) => 2 * (mfn + 1))),
    )
  })

  test('renders HTML with tables and charts', () => {
    const data = getCompareData([run], { baseSlug: null })
    const html = getComparisonHtml(data, { generatedNote: 'test' })
    expect(html).toContain('Scenario comparison')
    expect(html).toContain('Compare test')
    expect(html).toContain('svg')
    expect(html).toContain('Data table')
  })

  test('rejects more than 8 scenarios', () => {
    const runs = _.range(9).map(() => run)
    const data = getCompareData(runs, {})
    expect(() => getComparisonHtml(data, { generatedNote: 'x' })).toThrow(/at most 8/)
  })
})
