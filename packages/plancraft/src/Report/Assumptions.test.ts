import { GeneratedGrid } from '../Grid/GenerateGrid'
import { ScenarioFile, scenarioFileSchema } from '../Schema/ScenarioSchema'
import { getAssumptionsData, getAssumptionsHtml } from './Assumptions'

const base = (): ScenarioFile =>
  scenarioFileSchema.parse({
    plancraft: 1,
    meta: { name: 'Base', anchorYear: 2026 },
    household: {
      person1: { currentAge: { years: 37 }, retirementAge: { years: 65 }, maxAge: { years: 95 } },
      person2: { currentAge: { years: 37 }, retirementAge: { years: 65 }, maxAge: { years: 95 } },
      withdrawalStart: 'person1',
    },
    portfolio: { balance: 400000 },
    events: [
      {
        id: 'save',
        label: 'Net investable savings',
        kind: 'savings',
        amount: { perYear: 103000 },
        timing: {
          from: { named: 'now' },
          to: { named: 'lastWorkingMonth', person: 'person1' },
        },
      },
      {
        id: 'tuition',
        label: 'Private school',
        kind: 'expenseEssential',
        amount: { perYear: 60000 },
        timing: { from: { calendarYear: 2032, month: 9 }, to: { calendarYear: 2045, month: 6 } },
        growth: { annualPercent: 2 },
      },
    ],
    simulation: {
      expectedReturns: { fixed: { stocks: 0.05, bonds: 0.02 } },
      inflation: { manual: 0.024 },
      sampling: { type: 'monteCarlo', numRuns: 2000, seed: 1776 },
      legacy: 0,
    },
  })

const generated = (): GeneratedGrid =>
  ({
    base: base(),
    grid: {
      plancraftGrid: 1,
      name: 'G',
      base: 'base.scenario.json',
      dimensions: [
        {
          id: 'legacy',
          name: 'Legacy target',
          variants: [
            { id: 'none', name: 'No legacy', simulation: { legacy: 0 } },
            { id: 'm5', name: 'Leave $5M', simulation: { legacy: 5000000 } },
          ],
        },
        {
          id: 'house',
          name: 'House',
          variants: [
            {
              id: 'cheap',
              name: 'Cheap house',
              events: [
                {
                  id: 'house-pi',
                  label: 'Mortgage principal and interest',
                  kind: 'expenseEssential',
                  nominal: true,
                  amount: { perYear: 39720 },
                  timing: {
                    from: { calendarYear: 2027, month: 1 },
                    to: { calendarYear: 2056, month: 12 },
                  },
                },
                // Replaces the base savings flow, which the report must say.
                {
                  id: 'save',
                  label: 'Net investable savings',
                  kind: 'savings',
                  amount: { perYear: 90000 },
                  timing: {
                    from: { named: 'now' },
                    to: { named: 'lastWorkingMonth', person: 'person1' },
                  },
                },
              ],
            },
            {
              id: 'retire70',
              name: 'Work to 70',
              household: { person1: { retirementAge: { years: 70 } } },
              excludeEventIds: ['tuition'],
            },
          ],
        },
      ],
    },
    combos: [],
    conditions: [
      {
        id: 'pessimistic',
        name: 'Pessimistic',
        simulation: { expectedReturns: { fixed: { stocks: 0.035, bonds: 0.015 } } },
      },
    ],
  }) as unknown as GeneratedGrid

describe('assumptions', () => {
  const d = getAssumptionsData(generated())

  it('reports the household, portfolio and anchor year', () => {
    expect(d.anchorYear).toBe(2026)
    expect(d.portfolio).toBe(400000)
    expect(d.people).toHaveLength(2)
    expect(d.people[0]).toEqual({
      id: 'Person 1', currentAge: '37', retirementAge: '65', maxAge: '95',
    })
    expect(d.withdrawalStart).toBe('person 1')
  })

  it('spells out a zero legacy rather than omitting it', () => {
    const legacy = d.simulation.find((x) => x.label === 'Legacy target (real)')
    expect(legacy?.value).toContain('$0')
    expect(legacy?.value).toContain('amortized to zero')
  })

  it('reports expected returns as real, and the seed', () => {
    expect(d.simulation).toContainEqual({
      label: 'Expected real returns', value: '5.00% stocks / 2.00% bonds',
    })
    expect(d.simulation.find((x) => x.label === 'Sampling')?.value).toContain('seed 1776')
  })

  it('formats amounts, timings and growth of base flows', () => {
    const tuition = d.baseEvents.find((e) => e.id === 'tuition')!
    expect(tuition.amount).toBe('$60,000/yr')
    expect(tuition.timing).toBe('Sep 2032 → Jun 2045')
    expect(tuition.notes).toBe('+2%/yr')
    const save = d.baseEvents.find((e) => e.id === 'save')!
    expect(save.timing).toBe('now → person 1 last working month')
  })

  it('surfaces a variant-level simulation override', () => {
    const m5 = d.dimensions[0]!.variants.find((v) => v.id === 'm5')!
    expect(m5.settings).toContainEqual({
      label: 'Legacy target (real)', value: '$5,000,000',
    })
  })

  it('flags nominal flows and flows that replace a base flow', () => {
    const cheap = d.dimensions[1]!.variants.find((v) => v.id === 'cheap')!
    expect(cheap.events.find((e) => e.id === 'house-pi')!.notes).toContain('nominal')
    expect(cheap.replacedEventIds).toEqual(['save'])
  })

  it('reports household overrides and excluded flows', () => {
    const v = d.dimensions[1]!.variants.find((v) => v.id === 'retire70')!
    expect(v.settings).toContainEqual({ label: 'Person 1 retires at', value: '70' })
    expect(v.excludedEventIds).toEqual(['tuition'])
  })

  it('describes conditions by what they override', () => {
    expect(d.conditions[0]!.settings).toContainEqual({
      label: 'Expected real returns', value: '3.50% stocks / 1.50% bonds',
    })
  })

  it('renders html containing the critical inputs', () => {
    const html = getAssumptionsHtml(d)
    expect(html).toContain('Private school')
    expect(html).toContain('$60,000/yr')
    expect(html).toContain('amortized to zero')
    expect(html).toContain('nominal')
    expect(html).not.toContain('<script')
  })
})
