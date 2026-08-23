import { ScenarioFile, scenarioFileSchema } from '../Schema/ScenarioSchema'
import { compileScenario } from './CompileToPlanParams'
import { getCompilationReport, getYearRows } from './CompilationReport'
import { resolveScenario, ScenarioError } from './ResolveScenario'
import { deterministicSmallId } from './ResolveMonths'

const NOW = 1755950400000 // 2026-08-23 UTC, fixed for tests.

const baseScenario = (): ScenarioFile =>
  scenarioFileSchema.parse({
    plancraft: 1,
    meta: { name: 'Test household', anchorYear: 2026 },
    household: {
      person1: {
        currentAge: { years: 37 },
        retirementAge: { years: 55 },
        maxAge: { years: 95 },
      },
      person2: {
        currentAge: { years: 38 },
        retirementAge: { years: 52 },
        maxAge: { years: 95 },
      },
      withdrawalStart: 'person1',
    },
    portfolio: { balance: 621000 },
    events: [
      {
        id: 'save-fellowship',
        label: 'Savings through fellowship',
        kind: 'savings',
        amount: { perYear: 120000 },
        timing: { from: { named: 'now' }, to: { calendarYear: 2028, month: 6 } },
      },
      {
        id: 'save-attending',
        kind: 'savings',
        amount: { perYear: 160000 },
        timing: {
          from: { calendarYear: 2028, month: 7 },
          to: { named: 'lastWorkingMonth' },
        },
      },
      {
        id: 'house-down-payment',
        kind: 'expenseEssential',
        amount: { oneTime: 400000 },
        timing: { at: { calendarYear: 2031 } },
      },
      {
        id: 'daycare',
        kind: 'expenseEssential',
        amount: { perMonth: 2000 },
        timing: { from: { calendarYear: 2028 }, durationYears: 4 },
      },
      {
        id: 'social-security',
        kind: 'retirementIncome',
        amount: { perMonth: 3000 },
        timing: {
          from: { age: { person: 'person1', years: 70 } },
          to: { named: 'maxAge' },
        },
      },
    ],
    simulation: {
      expectedReturns: { fixed: { stocks: 0.05, bonds: 0.02 } },
      inflation: { manual: 0.024 },
      sampling: { type: 'monteCarlo', numRuns: 500, seed: 42 },
    },
  })

describe('compileScenario', () => {
  test('compiles a realistic scenario through guard + normalization', () => {
    const compiled = compileScenario(baseScenario(), { now: NOW })
    expect(compiled.planParams.v).toBe(30)
    // Anchor is Jan 2026 (anchorYear set), person1 is 37y => withdrawal at 55y.
    expect(compiled.withdrawalStartMFN).toBe((55 - 37) * 12)
    expect(compiled.numMonthsSimulated).toBe((95 - 37) * 12 + 1)
    expect(Object.keys(compiled.planParams.wealth.futureSavings)).toHaveLength(2)
    expect(
      Object.keys(compiled.planParams.adjustmentsToSpending.extraSpending.essential),
    ).toHaveLength(2)
    expect(compiled.simulationArgs).toEqual({
      numRuns: 500,
      seed: 42,
      percentiles: [5, 25, 50, 75, 95],
    })

    // Schedules: fellowship savings from month 0 through 2028-06 (MFN 29).
    const fellowship = compiled.schedules.find(
      (x) => x.eventId === 'save-fellowship',
    )!
    expect(fellowship.mfnStart).toBe(0)
    expect(fellowship.mfnEnd).toBe((2028 - 2026) * 12 + 6 - 1) // 29
    expect(fellowship.perMonthAmount).toBe(10000)

    // One-time house purchase at Jan 2031 => MFN 60.
    const house = compiled.schedules.find((x) => x.eventId === 'house-down-payment')!
    expect(house.mfnStart).toBe(60)
    expect(house.isOneTime).toBe(true)

    // Attending savings end at last working month.
    const attending = compiled.schedules.find((x) => x.eventId === 'save-attending')!
    expect(attending.mfnEnd).toBe(compiled.withdrawalStartMFN - 1)
  })

  test('savings extending past retirement is rejected with a clear error', () => {
    const scenario = baseScenario()
    scenario.events = [
      {
        id: 'bad-savings',
        kind: 'savings',
        amount: { perMonth: 1000 },
        timing: {
          from: { named: 'now' },
          to: { age: { person: 'person1', years: 60 } }, // past retirement at 55
        },
      },
    ]
    expect(() => compileScenario(scenario, { now: NOW })).toThrow(ScenarioError)
    expect(() => compileScenario(scenario, { now: NOW })).toThrow(
      /savings event 'bad-savings'/,
    )
  })

  test('one-time amount requires {at} timing', () => {
    const scenario = baseScenario()
    scenario.events = [
      {
        id: 'bad-timing',
        kind: 'expenseEssential',
        amount: { oneTime: 1000 },
        timing: { from: { named: 'now' }, durationYears: 1 },
      },
    ]
    expect(() => compileScenario(scenario, { now: NOW })).toThrow(/one-time/)
  })

  test('calendar timing in the past is rejected', () => {
    const scenario = baseScenario()
    scenario.events = [
      {
        id: 'past-event',
        kind: 'expenseEssential',
        amount: { oneTime: 1000 },
        timing: { at: { calendarYear: 2020 } },
      },
    ]
    expect(() => compileScenario(scenario, { now: NOW })).toThrow(/in the past/)
  })

  test('report renders and year rows aggregate correctly', () => {
    const compiled = compileScenario(baseScenario(), { now: NOW })
    const rows = getYearRows(compiled)
    // 2026: 12 months of fellowship savings.
    expect(rows[0]!.savings).toBe(120000)
    // 2031: house down payment year plus 12 months of daycare ($24k).
    const y2031 = rows.find((x) => x.calendarYear === 2031)!
    expect(y2031.expenseEssential).toBe(400000 + 24000)
    // Savings are $160k/yr -> $13,333/mo (whole-dollar rounding) -> $159,996/yr.
    expect(y2031.savings).toBe(13333 * 12)
    expect(y2031.netFlow).toBe(13333 * 12 - 424000)
    const report = getCompilationReport(compiled)
    expect(report).toContain('house-down-payment')
    expect(report).toContain('| 2031 |')
  })

  test('single person, already retired household compiles', () => {
    const scenario = scenarioFileSchema.parse({
      plancraft: 1,
      meta: { name: 'Retired', anchorYear: 2026 },
      household: {
        person1: {
          currentAge: { years: 65 },
          retirementAge: { years: 65 },
        },
      },
      portfolio: { balance: 1500000 },
      events: [
        {
          id: 'ss',
          kind: 'retirementIncome',
          amount: { perMonth: 2500 },
          timing: {
            from: { age: { years: 70 } },
            to: { named: 'maxAge' },
          },
        },
      ],
    })
    const compiled = compileScenario(scenario, { now: NOW })
    expect(compiled.withdrawalStartMFN).toBe(0)
  })

  test('savings events rejected for already-retired household', () => {
    const scenario = scenarioFileSchema.parse({
      plancraft: 1,
      meta: { name: 'Retired', anchorYear: 2026 },
      household: {
        person1: { currentAge: { years: 65 }, retirementAge: { years: 65 } },
      },
      portfolio: { balance: 1500000 },
      events: [
        {
          id: 'save',
          kind: 'savings',
          amount: { perMonth: 100 },
          timing: { from: { named: 'now' }, durationYears: 1 },
        },
      ],
    })
    expect(() => compileScenario(scenario, { now: NOW })).toThrow(
      /already retired/,
    )
  })
})

describe('resolveScenario composition', () => {
  const files: Record<string, unknown> = {
    '/s/base.json': {
      plancraft: 1,
      meta: { name: 'Base', anchorYear: 2026 },
      household: {
        person1: { currentAge: { years: 40 }, retirementAge: { years: 65 } },
      },
      portfolio: { balance: 100000 },
      events: [
        {
          id: 'save',
          kind: 'savings',
          amount: { perMonth: 3000 },
          timing: { from: { named: 'now' }, to: { named: 'lastWorkingMonth' } },
        },
        {
          id: 'travel',
          kind: 'expenseDiscretionary',
          amount: { perYear: 12000 },
          timing: { from: { named: 'retirement' }, durationYears: 10 },
        },
      ],
    },
    '/s/variant.json': {
      plancraft: 1,
      meta: { name: 'Variant: bigger save' },
      composition: { extends: 'base.json', excludeEventIds: ['travel'] },
      events: [
        {
          id: 'save',
          kind: 'savings',
          amount: { perMonth: 5000 },
          timing: { from: { named: 'now' }, to: { named: 'lastWorkingMonth' } },
        },
      ],
    },
    '/s/fragment.json': {
      plancraft: 1,
      events: [
        {
          id: 'car',
          kind: 'expenseEssential',
          amount: { oneTime: 35000 },
          timing: { at: { calendarYear: 2027 } },
        },
      ],
    },
    '/s/with-fragment.json': {
      plancraft: 1,
      meta: { name: 'With fragment' },
      composition: { extends: 'base.json', include: ['fragment.json'] },
    },
    '/s/cycle-a.json': {
      plancraft: 1,
      meta: { name: 'A' },
      composition: { extends: 'cycle-b.json' },
    },
    '/s/cycle-b.json': {
      plancraft: 1,
      meta: { name: 'B' },
      composition: { extends: 'cycle-a.json' },
    },
  }
  const readFile = (path: string) => {
    const data = files[path]
    if (data === undefined) throw new ScenarioError(`${path}: not found`)
    return JSON.stringify(data)
  }
  const resolvePath = (fromFile: string, relative: string) =>
    fromFile.slice(0, fromFile.lastIndexOf('/') + 1) + relative

  test('extends merges non-event fields and events by id', () => {
    const resolved = resolveScenario('/s/variant.json', readFile, resolvePath)
    expect(resolved.meta.name).toBe('Variant: bigger save')
    expect(resolved.meta.anchorYear).toBe(2026) // inherited
    expect(resolved.portfolio.balance).toBe(100000) // inherited
    expect(resolved.events).toHaveLength(1) // save replaced, travel excluded
    const save = resolved.events[0]!
    expect(save.amount).toEqual({ perMonth: 5000 })
    // And it compiles.
    compileScenario(resolved, { now: 1755950400000 })
  })

  test('include merges fragments', () => {
    const resolved = resolveScenario('/s/with-fragment.json', readFile, resolvePath)
    expect(resolved.events.map((x) => x.id).sort()).toEqual([
      'car',
      'save',
      'travel',
    ])
  })

  test('cycles are detected', () => {
    expect(() =>
      resolveScenario('/s/cycle-a.json', readFile, resolvePath),
    ).toThrow(/circular/)
  })

  test('unknown excludeEventIds error', () => {
    const bad = {
      ...(files['/s/variant.json'] as object),
      composition: { extends: 'base.json', excludeEventIds: ['nope'] },
    }
    const readWithBad = (p: string) =>
      p === '/s/bad.json' ? JSON.stringify(bad) : readFile(p)
    expect(() =>
      resolveScenario('/s/bad.json', readWithBad, resolvePath),
    ).toThrow(/nope/)
  })
})

describe('deterministicSmallId', () => {
  test('is stable, 10 chars, lowercase', () => {
    const id = deterministicSmallId('house-down-payment')
    expect(id).toHaveLength(10)
    expect(id).toMatch(/^[a-z]{10}$/)
    expect(deterministicSmallId('house-down-payment')).toBe(id)
    expect(deterministicSmallId('other')).not.toBe(id)
  })
})
