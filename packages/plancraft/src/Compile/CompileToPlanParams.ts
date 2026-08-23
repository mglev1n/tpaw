import {
  CalendarDay,
  LabeledAmountTimed,
  LabeledAmountTimedList,
  Person,
  PlanParams,
  PlanParamsNormalized,
  getFullDatelessDefaultPlanParams,
  normalizePlanParams,
  planParamsGuard,
} from '@tpaw/common'
import _ from 'lodash'
import { EventKind, ScenarioEvent, ScenarioFile } from '../Schema/ScenarioSchema'
import {
  Anchor,
  HouseholdAges,
  PersonAges,
  ResolvedRange,
  ResolvedTimePoint,
  deterministicSmallId,
  getHouseholdAges,
  resolveTimePoint,
  resolveTimingRange,
} from './ResolveMonths'
import { ScenarioError } from './ResolveScenario'

// Per-event schedule in MFN (months-from-now) terms, used for reports and
// derived contribution tables. Compiled independently of (and cross-checked
// against) the planner's own normalization.
export type EventSchedule = {
  eventId: string
  label: string
  kind: EventKind
  nominal: boolean
  // Both inclusive. For one-time events start === end.
  mfnStart: number
  mfnEnd: number
  perMonthAmount: number
  isOneTime: boolean
}

export type SimulationArgs = {
  numRuns: number
  seed: number
  percentiles: number[]
}

export type CompiledScenario = {
  scenario: ScenarioFile
  planParams: PlanParams
  norm: PlanParamsNormalized
  ages: HouseholdAges
  anchor: Anchor
  schedules: EventSchedule[]
  simulationArgs: SimulationArgs
  numMonthsSimulated: number
  withdrawalStartMFN: number
}

const DEFAULT_SEED = 1776
const DEFAULT_NUM_RUNS = 2000
const DEFAULT_PERCENTILES = [5, 25, 50, 75, 95]

const _round3 = (x: number) => _.round(x, 3)

const _kindToLocation = {
  savings: 'futureSavings',
  retirementIncome: 'incomeDuringRetirement',
  expenseEssential: 'extraSpendingEssential',
  expenseDiscretionary: 'extraSpendingDiscretionary',
} as const

export const compileScenario = (
  scenario: ScenarioFile,
  opts: { now?: number } = {},
): CompiledScenario => {
  const now = opts.now ?? Date.now()
  const ages = getHouseholdAges(scenario.household)
  const anchorNow = new Date(now)
  const anchor: Anchor = {
    year: scenario.meta.anchorYear ?? anchorNow.getUTCFullYear(),
    month:
      scenario.meta.anchorYear !== undefined ? 1 : anchorNow.getUTCMonth() + 1,
  }

  const withdrawalStartPerson =
    scenario.household.person2 ? (scenario.household.withdrawalStart ?? 'person1') : 'person1'
  const withdrawalAges = ages[withdrawalStartPerson]
  if (withdrawalAges === null)
    throw new ScenarioError('withdrawalStart refers to a missing person2.')
  const withdrawalStartMFN =
    withdrawalAges.retirementAgeMonths === null
      ? 0
      : withdrawalAges.retirementAgeMonths - withdrawalAges.currentAgeMonths

  // ---- Events → entries + schedules ----
  const entriesByLocation: Record<
    (typeof _kindToLocation)[EventKind],
    LabeledAmountTimedList
  > = {
    futureSavings: {},
    incomeDuringRetirement: {},
    extraSpendingEssential: {},
    extraSpendingDiscretionary: {},
  }
  const schedules: EventSchedule[] = []
  const usedIds = new Set<string>()

  scenario.events.forEach((event, index) => {
    const context = `events[${index}] (id: ${event.id})`
    if (event.kind === 'savings' && withdrawalAges.retirementAgeMonths === null)
      throw new ScenarioError(
        `${context}: 'savings' events are not allowed when the household is ` +
          "already retired. Use kind 'retirementIncome'.",
      )

    const { resolved, amountAndTiming } = _resolveEvent(event, ages, anchor, context)

    let id = deterministicSmallId(event.id)
    while (usedIds.has(id)) id = deterministicSmallId(id + 'x')
    usedIds.add(id)

    const entry: LabeledAmountTimed = {
      label: event.label ?? event.id,
      nominal: event.nominal ?? false,
      id,
      sortIndex: index,
      colorIndex: index,
      amountAndTiming,
    }
    entriesByLocation[_kindToLocation[event.kind]][id] = entry
    schedules.push({
      eventId: event.id,
      label: entry.label ?? event.id,
      kind: event.kind,
      nominal: entry.nominal,
      ...resolved,
    })
  })

  // ---- PlanParams assembly ----
  const planParams = getFullDatelessDefaultPlanParams(now)
  if (scenario.meta.marketDataDate !== undefined) {
    planParams.datingInfo = {
      isDated: false,
      marketDataAsOfEndOfDayInNY: _parseCalendarDay(scenario.meta.marketDataDate),
    }
  }
  planParams.dialogPositionNominal = 'done'

  const toPerson = (p: PersonAges): Person => ({
    ages:
      p.retirementAgeMonths === null
        ? {
            type: 'retiredWithNoRetirementDateSpecified',
            currentAgeInfo: {
              isDatedPlan: false,
              currentAge: { inMonths: p.currentAgeMonths },
            },
            maxAge: { inMonths: p.maxAgeMonths },
          }
        : {
            type: 'retirementDateSpecified',
            currentAgeInfo: {
              isDatedPlan: false,
              currentAge: { inMonths: p.currentAgeMonths },
            },
            retirementAge: { inMonths: p.retirementAgeMonths },
            maxAge: { inMonths: p.maxAgeMonths },
          },
  })
  planParams.people = ages.person2
    ? {
        withPartner: true,
        person1: toPerson(ages.person1),
        person2: toPerson(ages.person2),
        withdrawalStart: withdrawalStartPerson,
      }
    : { withPartner: false, person1: toPerson(ages.person1) }

  planParams.wealth = {
    portfolioBalance: {
      isDatedPlan: false,
      amount: Math.round(scenario.portfolio.balance),
    },
    futureSavings: entriesByLocation.futureSavings,
    incomeDuringRetirement: entriesByLocation.incomeDuringRetirement,
  }
  planParams.adjustmentsToSpending.extraSpending = {
    essential: entriesByLocation.extraSpendingEssential,
    discretionary: entriesByLocation.extraSpendingDiscretionary,
  }

  _applySimulationSettings(scenario, planParams)

  // ---- Validate exactly as the product would ----
  const guardCheck = planParamsGuard(planParams)
  if (guardCheck.error)
    throw new ScenarioError(
      `Compiled PlanParams failed tpawplanner validation: ${guardCheck.message}`,
    )
  // normalizePlanParams internally asserts the normalize→inverse round-trip.
  const norm = normalizePlanParams(planParams, {
    timestamp: now,
    calendarDay: null,
  })
  _assertNoNormalizationErrors(norm, schedules)

  const simulation = scenario.simulation
  const sampling = simulation?.sampling
  const simulationArgs: SimulationArgs = {
    numRuns:
      sampling?.type === 'monteCarlo'
        ? (sampling.numRuns ?? DEFAULT_NUM_RUNS)
        : DEFAULT_NUM_RUNS,
    seed:
      sampling?.type === 'monteCarlo' ? (sampling.seed ?? DEFAULT_SEED) : DEFAULT_SEED,
    percentiles: simulation?.percentiles ?? DEFAULT_PERCENTILES,
  }

  const numMonthsSimulated =
    Math.max(
      ages.person1.maxAgeMonths - ages.person1.currentAgeMonths,
      ages.person2 ? ages.person2.maxAgeMonths - ages.person2.currentAgeMonths : 0,
    ) + 1

  return {
    scenario,
    planParams,
    norm,
    ages,
    anchor,
    schedules,
    simulationArgs,
    numMonthsSimulated,
    withdrawalStartMFN,
  }
}

const _resolveEvent = (
  event: ScenarioEvent,
  ages: HouseholdAges,
  anchor: Anchor,
  context: string,
): {
  resolved: Pick<
    EventSchedule,
    'mfnStart' | 'mfnEnd' | 'perMonthAmount' | 'isOneTime'
  >
  amountAndTiming: LabeledAmountTimed['amountAndTiming']
} => {
  if ('oneTime' in event.amount) {
    if (!('at' in event.timing))
      throw new ScenarioError(
        `${context}: a one-time amount needs timing of the form {at: ...}.`,
      )
    const at: ResolvedTimePoint = resolveTimePoint(
      event.timing.at,
      ages,
      anchor,
      `${context}.timing.at`,
    )
    const amount = Math.round(event.amount.oneTime)
    return {
      resolved: {
        mfnStart: at.mfn,
        mfnEnd: at.mfn,
        perMonthAmount: amount,
        isOneTime: true,
      },
      amountAndTiming: { type: 'oneTime', amount, month: at.month },
    }
  }

  if ('at' in event.timing)
    throw new ScenarioError(
      `${context}: a recurring amount (perMonth/perYear) needs a timing ` +
        'range ({from, to} or {from, durationYears}), not {at}.',
    )
  const range: ResolvedRange = resolveTimingRange(
    event.timing,
    ages,
    anchor,
    `${context}.timing`,
  )
  const perMonthAmount = Math.round(
    'perMonth' in event.amount ? event.amount.perMonth : event.amount.perYear / 12,
  )
  return {
    resolved: {
      mfnStart: range.start.mfn,
      mfnEnd: range.end.mfn,
      perMonthAmount,
      isOneTime: false,
    },
    amountAndTiming: {
      type: 'recurring',
      monthRange: {
        type: 'startAndEnd',
        start: range.start.month,
        end: range.end.month,
      },
      everyXMonths: 1,
      baseAmount: perMonthAmount,
      delta: null,
    },
  }
}

const _applySimulationSettings = (
  scenario: ScenarioFile,
  planParams: PlanParams,
) => {
  const s = scenario.simulation
  if (!s) return

  if (s.strategy) planParams.advanced.strategy = s.strategy

  if (s.expectedReturns) {
    planParams.advanced.returnsStatsForPlanning.expectedValue.empiricalAnnualNonLog =
      'fixed' in s.expectedReturns
        ? {
            type: 'fixed',
            stocks: _round3(s.expectedReturns.fixed.stocks),
            bonds: _round3(s.expectedReturns.fixed.bonds),
          }
        : { type: s.expectedReturns.preset }
  }

  if (s.inflation !== undefined) {
    planParams.advanced.annualInflation =
      s.inflation === 'suggested'
        ? { type: 'suggested' }
        : { type: 'manual', value: _round3(s.inflation.manual) }
  }

  if (s.sampling) {
    planParams.advanced.sampling =
      s.sampling.type === 'historical'
        ? { type: 'historical', defaultData: { monteCarlo: null } }
        : {
            type: 'monteCarlo',
            data: {
              blockSize: {
                inMonths: Math.max(
                  1,
                  Math.round((s.sampling.blockSizeYears ?? 5) * 12),
                ),
              },
              staggerRunStarts: s.sampling.staggerRunStarts ?? true,
            },
          }
  }

  if (s.riskTolerance !== undefined)
    planParams.risk.tpaw.riskTolerance.at20 = s.riskTolerance
  if (s.spendingCeiling !== undefined)
    planParams.adjustmentsToSpending.tpawAndSPAW.monthlySpendingCeiling =
      s.spendingCeiling === null ? null : Math.round(s.spendingCeiling)
  if (s.spendingFloor !== undefined)
    planParams.adjustmentsToSpending.tpawAndSPAW.monthlySpendingFloor =
      s.spendingFloor === null ? null : Math.round(s.spendingFloor)
  if (s.legacy !== undefined)
    planParams.adjustmentsToSpending.tpawAndSPAW.legacy.total = Math.round(s.legacy)
  if (s.stockAllocation) {
    planParams.risk.spawAndSWR.allocation.start.stocks = _.round(
      s.stockAllocation.start,
      2,
    )
    planParams.risk.spawAndSWR.allocation.end.stocks = _.round(
      s.stockAllocation.end,
      2,
    )
  }
  if (s.swrWithdrawal) {
    planParams.risk.swr.withdrawal =
      'percentPerYear' in s.swrWithdrawal
        ? { type: 'asPercentPerYear', percentPerYear: s.swrWithdrawal.percentPerYear }
        : {
            type: 'asAmountPerMonth',
            amountPerMonth: Math.round(s.swrWithdrawal.amountPerMonth),
          }
  }
}

const _parseCalendarDay = (yyyyMmDd: string): CalendarDay => {
  const [year, month, day] = yyyyMmDd.split('-').map((x) => parseInt(x, 10)) as [
    number,
    number,
    number,
  ]
  return { year, month, day }
}

// Walk every normalized entry and surface the planner's own range errors
// (e.g. a savings event extending past retirement), mapped back to scenario
// event ids.
const _assertNoNormalizationErrors = (
  norm: PlanParamsNormalized,
  schedules: EventSchedule[],
) => {
  const errors: string[] = []
  const entryLists: {
    location: string
    entries: {
      label: string | null
      amountAndTiming: { type: string } & Record<string, unknown>
    }[]
  }[] = [
    { location: 'savings', entries: norm.wealth.futureSavings },
    {
      location: 'retirementIncome',
      entries: norm.wealth.incomeDuringRetirement,
    },
    {
      location: 'expenseEssential',
      entries: norm.adjustmentsToSpending.extraSpending.essential,
    },
    {
      location: 'expenseDiscretionary',
      entries: norm.adjustmentsToSpending.extraSpending.discretionary,
    },
  ]

  const monthError = (x: unknown): string | null =>
    x && typeof x === 'object' && 'errorMsg' in x
      ? ((x as { errorMsg: string | null }).errorMsg ?? null)
      : null

  for (const { location, entries } of entryLists) {
    for (const entry of entries) {
      const at = entry.amountAndTiming
      const label = entry.label ?? '(unlabeled)'
      const addError = (msg: string) =>
        errors.push(`${location} event '${label}': ${msg}`)
      if (at.type === 'inThePast') {
        addError('is entirely in the past.')
      } else if (at.type === 'oneTime') {
        const err = monthError(at['month'])
        if (err) addError(err)
      } else if (at.type === 'recurring') {
        const monthRange = at['monthRange'] as Record<string, unknown>
        for (const key of ['start', 'end', 'duration']) {
          const err = key in monthRange ? monthError(monthRange[key]) : null
          if (err) addError(`${key}: ${err}`)
        }
      }
    }
  }
  if (errors.length > 0)
    throw new ScenarioError(
      'Scenario events are outside the ranges tpawplanner allows:\n' +
        errors.map((x) => `  - ${x}`).join('\n') +
        '\nHint: savings must end by the last working month (use ' +
        "retirementIncome for amounts after retirement); expenses can span " +
        'any months up to maxAge.',
    )
}
