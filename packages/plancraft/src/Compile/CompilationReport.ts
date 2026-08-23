import _ from 'lodash'
import {
  CompiledScenario,
  EventSchedule,
  scheduleAmountAt,
} from './CompileToPlanParams'

// The derived cash-flow schedule: for each month, the sum of each kind of
// flow. This is the "net contributions" view that the scenario abstraction
// exists to produce.
export type MonthlySchedule = {
  savings: number[]
  retirementIncome: number[]
  expenseEssential: number[]
  expenseDiscretionary: number[]
}

export const getMonthlySchedule = (
  schedules: EventSchedule[],
  numMonths: number,
): MonthlySchedule => {
  const result: MonthlySchedule = {
    savings: new Array<number>(numMonths).fill(0),
    retirementIncome: new Array<number>(numMonths).fill(0),
    expenseEssential: new Array<number>(numMonths).fill(0),
    expenseDiscretionary: new Array<number>(numMonths).fill(0),
  }
  for (const s of schedules) {
    const target = result[s.kind]
    for (let mfn = s.mfnStart; mfn <= Math.min(s.mfnEnd, numMonths - 1); mfn++)
      target[mfn] = (target[mfn] ?? 0) + scheduleAmountAt(s, mfn)
  }
  return result
}

export type YearRow = {
  yearIndex: number
  calendarYear: number
  person1Age: number
  person2Age: number | null
  savings: number
  retirementIncome: number
  expenseEssential: number
  expenseDiscretionary: number
  netFlow: number
}

export const getYearRows = (compiled: CompiledScenario): YearRow[] => {
  const { ages, anchor, numMonthsSimulated } = compiled
  const monthly = getMonthlySchedule(compiled.schedules, numMonthsSimulated)
  const numYears = Math.ceil(numMonthsSimulated / 12)
  return _.range(numYears).map((yearIndex) => {
    const from = yearIndex * 12
    const to = Math.min(from + 12, numMonthsSimulated)
    const sum = (xs: number[]) => _.sum(xs.slice(from, to))
    const savings = sum(monthly.savings)
    const retirementIncome = sum(monthly.retirementIncome)
    const expenseEssential = sum(monthly.expenseEssential)
    const expenseDiscretionary = sum(monthly.expenseDiscretionary)
    return {
      yearIndex,
      calendarYear: anchor.year + yearIndex,
      person1Age: Math.floor((ages.person1.currentAgeMonths + from) / 12),
      person2Age: ages.person2
        ? Math.floor((ages.person2.currentAgeMonths + from) / 12)
        : null,
      savings,
      retirementIncome,
      expenseEssential,
      expenseDiscretionary,
      netFlow: savings + retirementIncome - expenseEssential - expenseDiscretionary,
    }
  })
}

const _fmt = (x: number) =>
  x === 0 ? '' : x.toLocaleString('en-US', { maximumFractionDigits: 0 })

export const getCompilationReport = (compiled: CompiledScenario): string => {
  const { scenario, schedules } = compiled
  const lines: string[] = []
  lines.push(`# Compilation report: ${scenario.meta.name}`)
  lines.push('')
  if (scenario.meta.description) {
    lines.push(scenario.meta.description)
    lines.push('')
  }
  lines.push(
    `Anchor: ${compiled.anchor.year}-${String(compiled.anchor.month).padStart(2, '0')} | ` +
      `Portfolio: $${_fmt(compiled.planParams.wealth.portfolioBalance.isDatedPlan === false ? compiled.planParams.wealth.portfolioBalance.amount : 0)} | ` +
      `Strategy: ${compiled.planParams.advanced.strategy} | ` +
      `Withdrawals start at month ${compiled.withdrawalStartMFN} | ` +
      `Simulated months: ${compiled.numMonthsSimulated}`,
  )
  lines.push('')

  lines.push('## Events (resolved)')
  lines.push('')
  lines.push('| Event | Kind | Months (MFN) | Amount/mo | Note |')
  lines.push('|---|---|---|---|---|')
  for (const s of schedules) {
    lines.push(
      `| ${s.label} | ${s.kind} | ${
        s.isOneTime ? `${s.mfnStart}` : `${s.mfnStart}–${s.mfnEnd}`
      } | $${_fmt(s.perMonthAmount)} | ${s.isOneTime ? 'one-time' : ''}${
        s.annualGrowthPercent !== null ? `+${s.annualGrowthPercent}%/yr` : ''
      }${s.nominal ? ' nominal' : ''} |`,
    )
  }
  lines.push('')

  lines.push('## Derived annual schedule')
  lines.push('')
  lines.push('All amounts in real dollars per year (as compiled).')
  lines.push('')
  lines.push(
    '| Year | Age' +
      (compiled.ages.person2 ? ' (p1/p2)' : '') +
      ' | Savings | Retirement income | Essential expenses | Discretionary expenses | Net flow |',
  )
  lines.push('|---|---|---|---|---|---|---|')
  const rows = getYearRows(compiled)
  for (const r of rows) {
    const allZero =
      r.savings === 0 &&
      r.retirementIncome === 0 &&
      r.expenseEssential === 0 &&
      r.expenseDiscretionary === 0
    if (allZero) continue
    lines.push(
      `| ${r.calendarYear} | ${r.person1Age}${
        r.person2Age !== null ? `/${r.person2Age}` : ''
      } | ${_fmt(r.savings)} | ${_fmt(r.retirementIncome)} | ${_fmt(
        r.expenseEssential,
      )} | ${_fmt(r.expenseDiscretionary)} | ${_fmt(r.netFlow)} |`,
    )
  }
  lines.push('')
  return lines.join('\n')
}
