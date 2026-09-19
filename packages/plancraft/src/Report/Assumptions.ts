import _ from 'lodash'
import { GeneratedGrid } from '../Grid/GenerateGrid'
import { GridCondition } from '../Grid/GridSchema'
import {
  ScenarioEvent,
  ScenarioFile,
  ScenarioPerson,
  SimulationSettings,
  TimePoint,
} from '../Schema/ScenarioSchema'
import { _esc, _usd } from './HtmlReport'

// Every figure a report quotes comes from a scenario the simulator actually
// ran, but until this module the reports only carried the grid's prose
// description -- which is hand-written and can drift from the JSON. This
// renders the critical inputs (legacy target, expected returns, portfolio,
// savings, tuition, mortgage, and what each variant changes) straight from
// the generated grid, so the assumptions in the report cannot disagree with
// the ones that were simulated.

export type AssumptionEvent = {
  id: string
  label: string
  kind: string
  amount: string
  timing: string
  notes: string
}

// One standalone scenario's inputs. The grid form below is this plus the
// per-variant overlays; the comparison report comes as N independent
// scenarios instead, so it renders a list of these.
export type ScenarioAssumptions = {
  name: string
  anchorYear: number | null
  people: { id: string; currentAge: string; retirementAge: string; maxAge: string }[]
  withdrawalStart: string
  portfolio: number
  simulation: { label: string; value: string }[]
  events: AssumptionEvent[]
}

export type AssumptionsData = {
  anchorYear: number | null
  people: { id: string; currentAge: string; retirementAge: string; maxAge: string }[]
  withdrawalStart: string
  portfolio: number
  simulation: { label: string; value: string }[]
  baseEvents: AssumptionEvent[]
  dimensions: {
    id: string
    name: string
    variants: {
      id: string
      name: string
      settings: { label: string; value: string }[]
      events: AssumptionEvent[]
      replacedEventIds: string[]
      excludedEventIds: string[]
    }[]
  }[]
  conditions: { id: string; name: string; settings: { label: string; value: string }[] }[]
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const PERSON = (id: string | undefined) =>
  id === 'person2' ? 'person 2' : 'person 1'
const NAMED: Record<string, string> = {
  now: 'now',
  lastWorkingMonth: 'last working month',
  retirement: 'retirement',
  maxAge: 'end of plan',
}

const _age = (a: { years: number; months?: number }) =>
  a.months ? `${a.years}y ${a.months}m` : `${a.years}`

const _point = (p: TimePoint): string => {
  if ('calendarYear' in p)
    return `${MONTHS[(p.month ?? 1) - 1] ?? ''} ${p.calendarYear}`.trim()
  if ('age' in p) return `${PERSON(p.age.person)} age ${_age(p.age)}`
  if (p.named === 'now') return 'now'
  return `${PERSON(p.person)} ${NAMED[p.named] ?? p.named}`
}

const _timing = (e: ScenarioEvent): string => {
  const t = e.timing
  if ('at' in t) return _point(t.at)
  const from = _point(t.from)
  return 'to' in t
    ? `${from} → ${_point(t.to)}`
    : `${from}, ${t.durationYears} yr${t.durationYears === 1 ? '' : 's'}`
}

const _amount = (e: ScenarioEvent): string => {
  const a = e.amount
  if ('perYear' in a) return `${_usd(a.perYear)}/yr`
  if ('perMonth' in a) return `${_usd(a.perMonth)}/mo`
  return `${_usd(a.oneTime)} once`
}

const _notes = (e: ScenarioEvent): string =>
  [
    e.nominal ? 'nominal (erodes with inflation)' : null,
    e.growth ? `${e.growth.annualPercent > 0 ? '+' : ''}${e.growth.annualPercent}%/yr` : null,
  ]
    .filter((x): x is string => x !== null)
    .join(', ')

export const describeEvent = (e: ScenarioEvent): AssumptionEvent => ({
  id: e.id,
  label: e.label ?? e.id,
  kind: e.kind,
  amount: _amount(e),
  timing: _timing(e),
  notes: _notes(e),
})

const _person = (id: string, p: ScenarioPerson) => ({
  id,
  currentAge: _age(p.currentAge),
  retirementAge: _age(p.retirementAge),
  maxAge: p.maxAge ? _age(p.maxAge) : '100 (default)',
})

// Only the settings that change an answer. Anything left at a planner default
// is omitted rather than printed as "default", to keep the table short enough
// that the values which DO vary stand out.
export const describeSimulation = (
  s: SimulationSettings | undefined,
  { includeDefaults }: { includeDefaults: boolean },
): { label: string; value: string }[] => {
  const out: { label: string; value: string }[] = []
  const push = (label: string, value: string | null) => {
    if (value !== null) out.push({ label, value })
  }
  if (s?.strategy || includeDefaults)
    push('Strategy', s?.strategy ?? 'TPAW (default)')
  if (s?.expectedReturns && 'fixed' in s.expectedReturns) {
    const { stocks, bonds } = s.expectedReturns.fixed
    push('Expected real returns',
      `${(stocks * 100).toFixed(2)}% stocks / ${(bonds * 100).toFixed(2)}% bonds`)
  } else if (s?.expectedReturns) {
    push('Expected returns', 'historical')
  } else if (includeDefaults) {
    push('Expected returns', 'planner default')
  }
  if (s?.inflation === 'suggested') push('Inflation', 'market breakeven')
  else if (s?.inflation)
    push('Inflation', `${(s.inflation.manual * 100).toFixed(2)}%`)
  if (s?.legacy !== undefined || includeDefaults)
    push('Legacy target (real)',
      s?.legacy ? _usd(s.legacy) : '$0 — portfolio amortized to zero at end of plan')
  if (s?.spendingFloor) push('Spending floor', `${_usd(s.spendingFloor)}/mo`)
  if (s?.spendingCeiling) push('Spending ceiling', `${_usd(s.spendingCeiling)}/mo`)
  if (s?.riskTolerance !== undefined)
    push('Risk tolerance at 20', String(s.riskTolerance))
  if (s?.stockAllocation)
    push('Stock allocation',
      `${_pctOf(s.stockAllocation.start)} → ${_pctOf(s.stockAllocation.end)}`)
  if (s?.sampling || includeDefaults) {
    const sa = s?.sampling
    push('Sampling', sa
      ? sa.type === 'monteCarlo'
        ? `Monte Carlo, ${sa.numRuns ?? 2000} runs, seed ${sa.seed ?? 1776}` +
          (sa.blockSizeYears ? `, ${sa.blockSizeYears}-yr blocks` : '')
        : 'Rolling historical windows (deterministic)'
      : 'Monte Carlo, 2000 runs, seed 1776 (default)')
  }
  return out
}

const _pctOf = (x: number) => `${Math.round(x * 100)}%`

export const describeScenario = (s: ScenarioFile): ScenarioAssumptions => ({
  name: s.meta.name,
  anchorYear: s.meta.anchorYear ?? null,
  people: [
    _person('Person 1', s.household.person1),
    ...(s.household.person2 ? [_person('Person 2', s.household.person2)] : []),
  ],
  withdrawalStart: PERSON(s.household.withdrawalStart),
  portfolio: s.portfolio.balance,
  simulation: describeSimulation(s.simulation, { includeDefaults: true }),
  events: s.events.map(describeEvent),
})

export const getAssumptionsData = (generated: GeneratedGrid): AssumptionsData => {
  const base = generated.base
  const baseIds = new Set(base.events.map((e) => e.id))
  return {
    anchorYear: base.meta.anchorYear ?? null,
    people: [
      _person('Person 1', base.household.person1),
      ...(base.household.person2
        ? [_person('Person 2', base.household.person2)]
        : []),
    ],
    withdrawalStart: PERSON(base.household.withdrawalStart),
    portfolio: base.portfolio.balance,
    simulation: describeSimulation(base.simulation, { includeDefaults: true }),
    baseEvents: base.events.map(describeEvent),
    dimensions: generated.grid.dimensions.map((d) => ({
      id: d.id,
      name: d.name,
      variants: d.variants.map((v) => ({
        id: v.id,
        name: v.name,
        settings: _variantSettings(v, base),
        events: (v.events ?? []).map(describeEvent),
        replacedEventIds: (v.events ?? [])
          .map((e) => e.id)
          .filter((id) => baseIds.has(id)),
        excludedEventIds: v.excludeEventIds ?? [],
      })),
    })),
    conditions: generated.conditions.map((c: GridCondition) => ({
      id: c.id,
      name: c.name,
      settings: describeSimulation(c.simulation, { includeDefaults: false }),
    })),
  }
}

// Non-event overrides a variant applies: household ages, portfolio, and any
// simulation setting (a legacy dimension lives here, not in the events).
const _variantSettings = (
  v: { household?: unknown; portfolio?: unknown; simulation?: unknown },
  base: ScenarioFile,
): { label: string; value: string }[] => {
  const out: { label: string; value: string }[] = []
  const hh = v.household as ScenarioFile['household'] | undefined
  for (const key of ['person1', 'person2'] as const) {
    const p = hh?.[key] as Partial<ScenarioPerson> | undefined
    if (!p) continue
    const who = key === 'person1' ? 'Person 1' : 'Person 2'
    if (p.retirementAge) out.push({ label: `${who} retires at`, value: _age(p.retirementAge) })
    if (p.currentAge) out.push({ label: `${who} current age`, value: _age(p.currentAge) })
    if (p.maxAge) out.push({ label: `${who} plan until`, value: _age(p.maxAge) })
  }
  const pf = v.portfolio as ScenarioFile['portfolio'] | undefined
  if (pf?.balance !== undefined && pf.balance !== base.portfolio.balance)
    out.push({ label: 'Portfolio balance', value: _usd(pf.balance) })
  out.push(
    ...describeSimulation(v.simulation as SimulationSettings | undefined, {
      includeDefaults: false,
    }),
  )
  return out
}

// --- HTML -------------------------------------------------------------------

const _kv = (rows: { label: string; value: string }[]): string =>
  rows.length === 0
    ? ''
    : `<table class="kv">${rows
        .map((r) => `<tr><th>${_esc(r.label)}</th><td>${_esc(r.value)}</td></tr>`)
        .join('')}</table>`

const _eventTable = (events: AssumptionEvent[]): string =>
  events.length === 0
    ? '<p class="muted">No money flows of its own.</p>'
    : `<table class="assumptions"><thead><tr><th>Flow</th><th>Kind</th>` +
      `<th class="num">Amount</th><th>When</th><th>Notes</th></tr></thead><tbody>` +
      events
        .map(
          (e) =>
            `<tr><td>${_esc(e.label)}</td><td><span class="kind k-${_esc(e.kind)}">` +
            `${_esc(e.kind)}</span></td><td class="num">${_esc(e.amount)}</td>` +
            `<td>${_esc(e.timing)}</td><td class="muted">${_esc(e.notes)}</td></tr>`,
        )
        .join('') +
      '</tbody></table>'

export const ASSUMPTIONS_STYLE = `
details.assumptions-block{border:1px solid var(--line);border-radius:8px;
  margin:16px 0;background:var(--surface)}
details.assumptions-block>summary{cursor:pointer;padding:12px 16px;font-weight:600}
details.assumptions-block>div{padding:0 16px 16px}
table.assumptions,table.kv{border-collapse:collapse;width:100%;margin:8px 0 16px;
  font-size:13px}
table.assumptions th,table.assumptions td,table.kv th,table.kv td{
  border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;
  vertical-align:top}
table.kv th{width:34%;font-weight:600;white-space:nowrap}
.assumptions .num,.assumptions th.num{text-align:right;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.assumptions .muted,p.muted{color:var(--muted)}
span.kind{font-size:11px;padding:1px 6px;border-radius:10px;white-space:nowrap;
  border:1px solid var(--line)}
.k-savings{background:#e3f2e3}.k-retirementIncome{background:#e3eefa}
.k-expenseEssential{background:#fae3e3}.k-expenseDiscretionary{background:#faf3e3}
@media (prefers-color-scheme:dark){
  .k-savings{background:#1f3a1f}.k-retirementIncome{background:#1b2c42}
  .k-expenseEssential{background:#3d1f1f}.k-expenseDiscretionary{background:#3a3320}}
.variant-block{margin:14px 0 0;padding-left:12px;border-left:3px solid var(--line)}
.variant-block h4{margin:0 0 4px;font-size:14px}
`

export const getAssumptionsHtml = (d: AssumptionsData): string => {
  const people = `<table class="assumptions"><thead><tr><th>Person</th>` +
    `<th class="num">Age now</th><th class="num">Retires at</th>` +
    `<th class="num">Plan until</th></tr></thead><tbody>` +
    d.people
      .map(
        (p) =>
          `<tr><td>${_esc(p.id)}</td><td class="num">${_esc(p.currentAge)}</td>` +
          `<td class="num">${_esc(p.retirementAge)}</td>` +
          `<td class="num">${_esc(p.maxAge)}</td></tr>`,
      )
      .join('') +
    '</tbody></table>'

  const dims = d.dimensions
    .map((dim) => {
      const variants = dim.variants
        .map((v) => {
          const notes = [
            v.replacedEventIds.length
              ? `replaces base flow${v.replacedEventIds.length === 1 ? '' : 's'}: ` +
                v.replacedEventIds.join(', ')
              : null,
            v.excludedEventIds.length
              ? `removes: ${v.excludedEventIds.join(', ')}`
              : null,
          ].filter((x): x is string => x !== null)
          return (
            `<div class="variant-block"><h4>${_esc(v.name)} ` +
            `<span class="muted">(${_esc(v.id)})</span></h4>` +
            (notes.length ? `<p class="muted">${_esc(notes.join('; '))}</p>` : '') +
            _kv(v.settings) +
            _eventTable(v.events) +
            '</div>'
          )
        })
        .join('')
      return `<h3>${_esc(dim.name)} <span class="muted">(${_esc(dim.id)})</span></h3>${variants}`
    })
    .join('')

  const conditions = d.conditions.length
    ? '<h3>Conditions (states of the world)</h3>' +
      d.conditions
        .map(
          (c) =>
            `<div class="variant-block"><h4>${_esc(c.name)} ` +
            `<span class="muted">(${_esc(c.id)})</span></h4>${_kv(c.settings)}</div>`,
        )
        .join('')
    : ''

  return (
    `<details class="assumptions-block"><summary>Model inputs — every ` +
    `assumption behind these numbers</summary><div>` +
    `<p class="muted">Rendered from the scenario files the simulator ran, not ` +
    `written by hand. All amounts are real ` +
    `${d.anchorYear ? d.anchorYear : 'present-day'} dollars, after tax, unless a ` +
    `flow is marked nominal.</p>` +
    `<h3>Household</h3>${people}` +
    `<p class="muted">Portfolio withdrawals begin at ${_esc(d.withdrawalStart)}'s ` +
    `retirement.</p>` +
    _kv([{ label: 'Starting portfolio', value: _usd(d.portfolio) }]) +
    `<h3>Simulation</h3>${_kv(d.simulation)}` +
    `<h3>Money flows common to every combination</h3>${_eventTable(d.baseEvents)}` +
    `<h3>What each decision changes</h3>` +
    `<p class="muted">Each variant below overlays these on the base above. A flow ` +
    `whose id matches a base flow replaces it.</p>${dims}${conditions}` +
    `</div></details>`
  )
}

// --- Comparison report ------------------------------------------------------

// Scenarios in a comparison are independent files rather than overlays on a
// shared base, so there is no "what changed" to render. Instead each is shown
// in full, and any setting that is identical across all of them is pulled out
// into a shared block so the differences are what remain per scenario.
export const getScenarioAssumptionsHtml = (
  list: ScenarioAssumptions[],
): string => {
  if (list.length === 0) return ''
  const first = list[0]!
  const same = (pick: (s: ScenarioAssumptions) => string) =>
    list.every((s) => pick(s) === pick(first))
  const kvKey = (s: ScenarioAssumptions) => JSON.stringify(s.simulation)
  const peopleKey = (s: ScenarioAssumptions) => JSON.stringify(s.people)
  const sharedSim = same(kvKey)
  const sharedPeople = same(peopleKey)
  const sharedPortfolio = list.every((s) => s.portfolio === first.portfolio)

  const peopleTable = (s: ScenarioAssumptions) =>
    `<table class="assumptions"><thead><tr><th>Person</th>` +
    `<th class="num">Age now</th><th class="num">Retires at</th>` +
    `<th class="num">Plan until</th></tr></thead><tbody>` +
    s.people
      .map(
        (p) =>
          `<tr><td>${_esc(p.id)}</td><td class="num">${_esc(p.currentAge)}</td>` +
          `<td class="num">${_esc(p.retirementAge)}</td>` +
          `<td class="num">${_esc(p.maxAge)}</td></tr>`,
      )
      .join('') +
    '</tbody></table>'

  const shared =
    (sharedPeople ? `<h3>Household</h3>${peopleTable(first)}` : '') +
    (sharedPortfolio
      ? _kv([{ label: 'Starting portfolio', value: _usd(first.portfolio) }])
      : '') +
    (sharedSim ? `<h3>Simulation</h3>${_kv(first.simulation)}` : '')

  const per = list
    .map(
      (s) =>
        `<div class="variant-block"><h4>${_esc(s.name)}</h4>` +
        (sharedPeople ? '' : `${peopleTable(s)}`) +
        (sharedPortfolio
          ? ''
          : _kv([{ label: 'Starting portfolio', value: _usd(s.portfolio) }])) +
        (sharedSim ? '' : _kv(s.simulation)) +
        _eventTable(s.events) +
        '</div>',
    )
    .join('')

  return (
    `<details class="assumptions-block"><summary>Model inputs \u2014 every ` +
    `assumption behind these numbers</summary><div>` +
    `<p class="muted">Rendered from the scenario files the simulator ran, not ` +
    `written by hand. All amounts are real ` +
    `${first.anchorYear ? first.anchorYear : 'present-day'} dollars, after tax, ` +
    `unless a flow is marked nominal.</p>` +
    (shared
      ? shared +
        `<p class="muted">The above is identical across every scenario ` +
        `compared. What differs is below.</p>`
      : '') +
    `<h3>Money flows by scenario</h3>${per}` +
    `</div></details>`
  )
}
