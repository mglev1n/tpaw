// Matched (paired) effect sizes over the budget-feasible region.
//
// A naive factorial grid averages a dimension's variants across every
// combination of the others -- including combinations that violate the
// household budget constraint, because house + schooling + loan payments
// compete with savings for the same net income. Those cells fail for an
// accounting reason rather than a financial-planning one, and they
// contaminate the averages unevenly (an expensive house survives only
// alongside a high savings rate, which biases its mean upward).
//
// Fix: for each dimension, consider each stratum of the OTHER dimensions.
// Keep the stratum only if every variant of the focal dimension is feasible
// there, so the comparison is like-for-like. Report the mean within-stratum
// spread.
const fs = require('fs')
// Usage: node analyze.js <canon.csv>  (produced by `plancraft grid ... --csv`)
const CSV = process.argv[2]
if (!CSV) { console.error('usage: node analyze.js <grid.csv>'); process.exit(1) }
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

const NET = 270_000
const SAV = { hyper: [110000, 0], high: [85000, 0], moderate: [62000, 0], creep: [85000, -2] }
const RET = { r55: 55, r60: 60, r65: 65, r70: 70 }
const LOAN = { aggressive: [48000, 5], standard: [29000, 10], idr: [19000, 20] }
const HOUSE = { modest: 0, typical: 14000, doctor: 30000 }
const BIRTH = [2027, 2029, 2031]

function meanContribution(r) {
  const wy = RET[r.retire] - 35
  const [amt, g] = SAV[r.savings]
  const [lpy, lyrs] = LOAN[r.loans]
  const nKids = r.education === 'three-public' ? 3 : 2
  const priv = r.education === 'two-private'
  let total = 0
  for (let t = 0; t < wy; t++) {
    const y = 2026 + t
    let edu = 0
    for (let i = 0; i < nKids; i++) {
      const b = BIRTH[i]
      if (y >= b && y <= b + 18) edu += 6000
      if (priv && y >= b + 5 && y <= b + 18) edu += 30000
      if (priv && y >= b + 18 && y <= b + 22) edu += 25000
    }
    total +=
      amt * Math.pow(1 + g / 100, t) -
      (y <= 2026 + lyrs - 1 ? lpy : 0) -
      (y >= 2027 && y <= 2056 ? HOUSE[r.housing] : 0) -
      edu
  }
  return total / wy
}

const DIMS = ['retire', 'savings', 'education', 'housing', 'loans']
const rows = load(CSV).map((r) => ({ ...r, contrib: meanContribution(r) }))

for (const FLOOR of [0, 10000]) {
  console.log(`\n${'='.repeat(72)}`)
  console.log(`MATCHED EFFECT SIZES  (feasible = mean annual net contribution >= ${usd(FLOOR)})`)
  console.log('='.repeat(72))
  const feasible = (r) => r.contrib >= FLOOR
  const kept = rows.filter((r) => r.condition === 'base-returns' && feasible(r)).length
  console.log(`Feasible combinations: ${kept}/432 at base returns\n`)

  for (const cond of ['pessimistic', 'base-returns', 'optimistic']) {
    const sub = rows.filter((r) => r.condition === cond)
    const results = DIMS.map((dim) => {
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
        if (group.length !== variants.length) continue
        if (!group.every(feasible)) continue // like-for-like only
        const vals = group.map((r) => r.medianRetirementSpendingPerMonth)
        spreads.push(Math.max(...vals) - Math.min(...vals))
        for (const r of group) perVariant[r[dim]].push(r.medianRetirementSpendingPerMonth)
      }
      return {
        dim,
        n: spreads.length,
        spread: spreads.length ? mean(spreads) : NaN,
        perVariant,
      }
    }).sort((a, b) => b.spread - a.spread)

    if (cond === 'base-returns') {
      console.log('Base returns — ranked, with matched variant means:')
      for (const e of results) {
        console.log(`  ${e.dim.padEnd(10)} ${usd(e.spread).padStart(9)}/mo   (${e.n} matched strata)`)
        for (const [v, vals] of Object.entries(e.perVariant))
          if (vals.length) console.log(`      ${v.padEnd(14)} ${usd(mean(vals))}/mo`)
      }
    } else {
      console.log(
        `${cond.padEnd(14)} ` +
          results.map((e) => `${e.dim} ${usd(e.spread)}`).join('  |  '),
      )
    }
  }
}

// Lifestyle-creep trade-off on a feasible, explicitly stated configuration.
console.log(`\n${'='.repeat(72)}`)
console.log('LIFESTYLE CREEP  (retire 65, standard loans, typical house, 2 kids public)')
console.log('='.repeat(72))
const HOLD = { retire: 'r65', loans: 'standard', housing: 'typical', education: 'two-public' }
const wy = 30, ry = 30
console.log(
  `${'variant'.padEnd(10)} ${'consume/yr'.padStart(11)} ${'retire/yr'.padStart(10)} ` +
    `${'ratio'.padStart(6)} ${'contrib/yr'.padStart(11)} ${'success'.padStart(8)}`,
)
const t = {}
for (const vid of Object.keys(SAV)) {
  const r = rows.find(
    (x) => x.condition === 'base-returns' && x.savings === vid &&
      Object.entries(HOLD).every(([k, v]) => x[k] === v),
  )
  const [amt, g] = SAV[vid]
  let tot = 0
  for (let i = 0; i < wy; i++) tot += amt * Math.pow(1 + g / 100, i)
  const avgSav = tot / wy
  const consume = NET - avgSav
  const retire = r.medianRetirementSpendingPerMonth * 12
  t[vid] = { avgSav, consume, retire }
  console.log(
    `${vid.padEnd(10)} ${usd(consume).padStart(11)} ${usd(retire).padStart(10)} ` +
      `${(retire / consume).toFixed(2).padStart(6)} ${usd(r.contrib).padStart(11)} ` +
      `${(100 * r.successProbability).toFixed(1).padStart(7)}%`,
  )
}
console.log('\nExchange rate (lifetime retirement dollars per dollar deferred):')
for (const [lo, hi] of [['moderate', 'high'], ['high', 'hyper'], ['creep', 'high']]) {
  const d = (t[hi].avgSav - t[lo].avgSav) * wy
  const gain = (t[hi].retire - t[lo].retire) * ry
  console.log(`  ${lo} -> ${hi}: defer ${usd(d)}, gain ${usd(gain)} = ${(gain / d).toFixed(2)}x`)
}
