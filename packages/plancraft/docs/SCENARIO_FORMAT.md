# Plancraft scenario format (v1)

A **scenario** describes a household's financial trajectory as a list of
decisions and events — income phases, expenses, one-time purchases — in
**real (inflation-adjusted), after-tax dollars**. Plancraft compiles it to a
standard [TPAW Planner](https://tpawplanner.com) plan, simulates it, and can
export a `.tpaw.txt` file you can open in the real planner UI.

The machine-readable contract is [`scenario.schema.json`](./scenario.schema.json)
(generated from the zod schema in `src/Schema/ScenarioSchema.ts`). This guide
covers the concepts and idioms.

## The mental model

TPAW models a single investment portfolio. Before retirement, **savings**
events add to it; at any time, **expense** events draw from it; after
retirement the strategy (TPAW by default) computes sustainable spending from
what remains, plus any **retirement income**. Regular living expenses before
retirement are *not* modeled — they are implicit in your net savings number.
That is the "net contributions" abstraction: you tell the planner what
actually reaches the portfolio, net of taxes and daily life.

So, to model a life decision, express it as its effect on cash flows:

| Decision | Events |
|---|---|
| Fellowship ends, attending salary starts mid-2028 | Two `savings` events with adjacent ranges: `$120k/yr` until 2028-06, `$160k/yr` from 2028-07 |
| Buy a house in 2031 ($400k down payment) | One-time `expenseEssential` at 2031, plus optionally a lower `savings` amount afterward (mortgage payments reduce surplus) |
| Daycare for 4 years from 2028 | `expenseEssential`, `perMonth: 2000`, `{from: {calendarYear: 2028}, durationYears: 4}` |
| Private school instead of public | `expenseEssential` for tuition years (put it in a variant file) |
| One spouse goes part-time in 2035 | Lower the `savings` amount from 2035 (split the savings event at that date) |
| One spouse retires early | Set that person's `retirementAge`; end their contribution to `savings` accordingly |
| Windfall / inheritance | One-time `savings` event (amounts must be ≥ 0 — never a negative expense) |
| Social Security at 70 | `retirementIncome`, `perMonth`, from `{age: {years: 70}}` to `{named: 'maxAge'}` |
| Moving to a higher-tax state in 2030 | Lower `savings` amounts from 2030 (you compute the net effect; plancraft is deliberately tax-naive) |

## Event kinds

- **`savings`** — net monthly/annual contribution to the portfolio before
  retirement. Must end by the last working month (of the `withdrawalStart`
  person). One-time savings = windfalls.
- **`retirementIncome`** — income arriving during retirement (Social
  Security, pension, annuity, part-time work in retirement).
- **`expenseEssential`** — must-fund expenses drawn from the portfolio at any
  time, pre- or post-retirement: mortgage years, daycare, tuition, a
  one-time down payment or car purchase. The planner funds these
  conservatively (bonds).
- **`expenseDiscretionary`** — nice-to-have expenses (travel, upgrades) the
  planner may scale back in poor markets.

## Timing

A **point** is one of:

```jsonc
{ "calendarYear": 2031, "month": 6 }          // calendar date (month optional, default January)
{ "age": { "person": "person2", "years": 52 } } // an age (person optional, default person1)
{ "named": "now" }                              // now
{ "named": "retirement", "person": "person1" }  // retirement month
{ "named": "lastWorkingMonth" }                 // month before retirement
{ "named": "maxAge" }                           // end of plan
```

Recurring events take a range `{ "from": <point>, "to": <point> }` (both
inclusive) or `{ "from": <point>, "durationYears": 4 }`. One-time events take
`{ "at": <point> }`.

## Growth

A recurring event can grow annually — e.g. salary growth flowing into
savings:

```jsonc
{ "id": "save", "kind": "savings",
  "amount": { "perYear": 160000 },
  "growth": { "annualPercent": 2.5 },
  "timing": { "from": { "calendarYear": 2028, "month": 7 }, "to": { "named": "lastWorkingMonth" } } }
```

Growth steps once a year on the anniversary of the range start (real growth
unless the event is `nominal`). The compiler expands a growing stream into
yearly-stepped plan entries, since the planner's own per-entry growth field
is declared but not implemented. Not allowed on one-time amounts.

Calendar dates are converted to ages using `meta.anchorYear` (the year "now"
is in). Set `anchorYear` explicitly so the scenario means the same thing
whenever it is compiled; with it set, "now" is January of that year.

## Composition: comparing decisions

Keep one base file and small variant files:

```jsonc
// base.scenario.json — the household, portfolio, and shared events.
// house-2031.scenario.json:
{
  "plancraft": 1,
  "meta": { "name": "Buy house 2031" },
  "composition": { "extends": "base.scenario.json" },
  "events": [
    { "id": "house", "kind": "expenseEssential",
      "amount": { "oneTime": 400000 }, "timing": { "at": { "calendarYear": 2031 } } }
  ]
}
```

- `extends`: inherit everything from a base file; fields here win; events
  merge **by id** (same id replaces the base's event — use this to change an
  amount in a variant).
- `include`: merge event-fragment files (`{ "plancraft": 1, "events": [...] }`).
- `excludeEventIds`: remove inherited events.

## Simulation settings

All optional. For reproducible comparisons, pin:

```jsonc
"simulation": {
  "expectedReturns": { "fixed": { "stocks": 0.05, "bonds": 0.02 } },
  "inflation": { "manual": 0.024 },
  "sampling": { "type": "monteCarlo", "numRuns": 2000, "seed": 1776 }
}
```

Keep `seed`, returns, and `numRuns` identical across scenarios you compare.
Amounts are rounded to whole dollars; returns/inflation to 0.1% steps
(planner requirements).

## What the compiler guarantees

Every compiled scenario passes the planner's own validation
(`planParamsGuard`) and normalization round-trip. Events that fall outside
allowed ranges (e.g. savings extending past retirement) are compile errors
with the planner's own messages — if plancraft accepts it, tpawplanner.com
accepts it.
