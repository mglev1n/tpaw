// Matched (paired) effect sizes over the budget-feasible region.
//
// A naive factorial grid averages a dimension's variants across every
// combination of the others -- including combinations that violate the
// household budget constraint, because house, schooling and loan payments
// compete with savings for the same net income. Those cells fail for an
// accounting reason rather than a financial-planning one, and they
// contaminate the averages unevenly (an expensive house survives only
// alongside a high savings rate, which biases its mean upward).
//
// Fix: for each dimension, walk the strata of the OTHER dimensions. Keep a
// stratum only if every variant of the focal dimension is budget-feasible
// there, so the comparison is like-for-like. Report the mean within-stratum
// spread.
//
// Usage: node analyze.js <grid.csv> <params.json> [feesGrid.csv]
const fs = require('fs')

const [, , CSV, PARAMS, FEES_CSV] = process.argv
if (!CSV || !PARAMS) {
  console.error('usage: node analyze.js <grid.csv> <params.json> [fees.csv]')
  process.exit(1)
}
const P = JSON.parse(fs.readFileSync(PARAMS, 'utf8'))

const load = (p) => {
  const [h, ...l] = fs.readFileSync(p, 'utf8').trim().split('\n')
  const c = h.split(',')
  return l.map((x) => {
    const v = x.split(',')
    const o = {}
    c.forEach((k, i) => (o[k] = isNaN(+v[i]) ? v[i] : +v[i]))
    return o
  })
}
const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length
const usd = (v) => '$' + Math.round(v).toLocaleString('en-US')

// Mean annual net portfolio contribution over the working years: gross
// savings less the obligations that compete with it.
function meanContribution(r) {
  const wy = P.retire[r.retire] - P.currentAge
  const [amt, g] = P.savings[r.savings]
  const [lpy, lyrs] = P.loans[r.loans]
  const [nKids, priv] = P.education[r.education]
  let total = 0
  for (let t = 0; t < wy; t++) {
    const y = 2026 + t
    let edu = 0
    for (let i = 0; i < nKids; i++) {
      const b = P.kidBirth[i]
      if (y >= b && y <= b + 18) edu += P.fivetwonine
      if (priv && y >= b + 5 && y <= b + 18) edu += P.privateK12
      if (priv && y >= b + 18 && y <= b + 22) edu += P.collegeTopUp
    }
    total +=
      amt * Math.pow(1 + g / 100, t) -
      (y <= 2026 + lyrs - 1 ? lpy : 0) -
      (y >= 2027 && y <= 2056 ? P.housing[r.housing] : 0) -
      edu
  }
  return total / wy
}

const DIMS = ['retire', 'savings', 'education', 'housing', 'loans']
const CONDS = ['pessimistic', 'base-returns', 'optimistic']
const rows = load(CSV).map((r) => ({ ...r, contrib: meanContribution(r) }))

console.log('#'.repeat(74))
console.log(`# ${P.label}`)
console.log(`# net ${usd(P.netIncome)}/yr, ${usd(P.portfolio)} invested, age ${P.currentAge}`)
console.log('#'.repeat(74))

function matched(sub, feasible) {
  return DIMS.map((dim) => {
    const others = DIMS.filter((d) => d !== dim)
    const strata = new Map()
    for (const r of sub) {
      const k = others.map((d) => r[d]).join('|')
      if (!strata.has(k)) strata.set(k, [])
      strata.get(k).push(r)
    }
    const variants = [...new Set(sub.map((r) => r[dim]))]
    const spreads = []
    const perVariant = Object.fromEntries(variants.map((v) => [v, []]))
    for (const [, group] of strata) {
      if (group.length !== variants.length || !group.every(feasible)) continue
      const vals = group.map((r) => r.medianRetirementSpendingPerMonth)
      spreads.push(Math.max(...vals) - Math.min(...vals))
      for (const r of group) perVariant[r[dim]].push(r.medianRetirementSpendingPerMonth)
    }
    return { dim, n: spreads.length, spread: spreads.length ? mean(spreads) : NaN, perVariant }
  }).sort((a, b) => b.spread - a.spread)
}

for (const FLOOR of [0, 10000]) {
  const feasible = (r) => r.contrib >= FLOOR
  console.log(`\n=== Matched effect sizes (feasible = mean contribution >= ${usd(FLOOR)}) ===`)
  console.log(
    `Feasible: ${rows.filter((r) => r.condition === 'base-returns' && feasible(r)).length}` +
      `/${rows.filter((r) => r.condition === 'base-returns').length} at base returns`,
  )
  for (const cond of CONDS) {
    const res = matched(rows.filter((r) => r.condition === cond), feasible)
    if (cond === 'base-returns') {
      console.log('\nBase returns, ranked:')
      for (const e of res) {
        console.log(`  ${e.dim.padEnd(10)} ${usd(e.spread).padStart(9)}/mo  (${e.n} strata)`)
        for (const [v, vals] of Object.entries(e.perVariant))
          if (vals.length) console.log(`      ${v.padEnd(14)} ${usd(mean(vals))}/mo`)
      }
    } else {
      console.log(`${cond.padEnd(14)} ` + res.map((e) => `${e.dim} ${usd(e.spread)}`).join('  |  '))
    }
  }
  console.log(`RANK ORDER @${usd(FLOOR)}: ` +
    CONDS.map((c) => matched(rows.filter((r) => r.condition === c), feasible)
      .map((e) => e.dim).join('>')).join('   ||   '))
}

// --- Lifestyle creep, on an explicitly stated feasible configuration --------
const HOLD = { retire: 'r65', loans: 'standard', housing: 'typical', education: 'two-public' }
const wy = P.retire.r65 - P.currentAge
const ry = 95 - P.retire.r65
// OECD-modified equivalence scale: first adult 1.0, each further adult 0.5,
// each child 0.3. A working household of four is 2.1 equivalent adults; a
// retired couple is 1.5. A raw dollar ratio of 1.0 therefore does NOT mean a
// level standard of living -- the same dollars support far fewer people once
// the children are gone, so per-person consumption rises sharply.
const EQ_WORKING = 1.0 + 0.5 + 0.3 + 0.3
const EQ_RETIRED = 1.0 + 0.5
console.log(`\n=== Lifestyle creep (retire 65, standard loans, typical house, 2 kids public) ===`)
console.log(
  `${'variant'.padEnd(10)} ${'consume/yr'.padStart(11)} ${'retire/yr'.padStart(10)} ` +
    `${'ratio'.padStart(6)} ${'per-equiv'.padStart(10)} ${'contrib/yr'.padStart(11)} ${'success'.padStart(8)}`,
)
const t = {}
for (const vid of Object.keys(P.savings)) {
  const r = rows.find(
    (x) => x.condition === 'base-returns' && x.savings === vid &&
      Object.entries(HOLD).every(([k, v]) => x[k] === v))
  if (!r) continue
  const [amt, g] = P.savings[vid]
  let tot = 0
  for (let i = 0; i < wy; i++) tot += amt * Math.pow(1 + g / 100, i)
  const avgSav = tot / wy
  const consume = P.netIncome - avgSav
  const retire = r.medianRetirementSpendingPerMonth * 12
  t[vid] = { avgSav, consume, retire }
  const perEquiv = (retire / EQ_RETIRED) / (consume / EQ_WORKING)
  console.log(
    `${vid.padEnd(10)} ${usd(consume).padStart(11)} ${usd(retire).padStart(10)} ` +
      `${(retire / consume).toFixed(2).padStart(6)} ${perEquiv.toFixed(2).padStart(10)} ` +
      `${usd(r.contrib).padStart(11)} ${(100 * r.successProbability).toFixed(1).padStart(7)}%`)
}
console.log('\nper-equiv: retirement vs working consumption PER EQUIVALENT ADULT.')
console.log('A raw ratio of 1.00 is not level living: the retired couple is 1.5 equivalent')
console.log('adults against 2.1 while the children are home, so per-person consumption rises.')
console.log('\nExchange rate (lifetime retirement dollars per dollar deferred):')
for (const [lo, hi] of [['moderate', 'high'], ['high', 'hyper'], ['creep', 'high']]) {
  if (!t[lo] || !t[hi]) continue
  const d = (t[hi].avgSav - t[lo].avgSav) * wy
  const gain = (t[hi].retire - t[lo].retire) * ry
  console.log(`  ${lo} -> ${hi}: defer ${usd(d)}, gain ${usd(gain)} = ${(gain / d).toFixed(2)}x`)
}

// --- Fee drag ---------------------------------------------------------------
if (FEES_CSV && fs.existsSync(FEES_CSV)) {
  const fees = load(FEES_CSV)
  const vs = [...new Set(fees.map((r) => r.fees))]
  const m = (v) => mean(fees.filter((r) => r.fees === v).map((r) => r.medianRetirementSpendingPerMonth))
  console.log('\n=== Fee drag (companion grid) ===')
  vs.forEach((v) => console.log(`  ${v.padEnd(9)} ${usd(m(v)).padStart(9)}/mo`))
  const spread = Math.max(...vs.map(m)) - Math.min(...vs.map(m))
  const sv = [...new Set(fees.map((r) => r.savings))]
  const ms = (v) => mean(fees.filter((r) => r.savings === v).map((r) => r.medianRetirementSpendingPerMonth))
  console.log(`  fee spread ${usd(spread)}/mo   (savings spread in same grid: ` +
    `${usd(Math.max(...sv.map(ms)) - Math.min(...sv.map(ms)))}/mo)`)
}
