#!/usr/bin/env python3
"""Pass 1 analysis: which levers move the floor. Usage: <grid-levers.csv>

Two hazards this has to avoid.

BUDGET INFEASIBILITY. A combination whose peak essential expenses exceed the
household's annual savings is unpayable, not merely risky. It reads 0% for an
accounting reason and, left in, drags down the mean of whichever variants
appear in it -- unevenly, because expensive schooling survives only alongside
a full-time second income. So feasibility is computed here from the same
functions that built the grid, and infeasible cells are censused separately
rather than ranked.

NAIVE MAIN EFFECTS. Averaging a dimension's variants across every combination
of the other five has the same contamination problem in milder form. The
ranking below is therefore MATCHED: for each dimension, walk the strata of
the other five, keep a stratum only where every variant of the focal
dimension is feasible, and report the mean within-stratum spread.
"""
import collections, csv, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


L = _load('levers', os.path.join(HERE, 'levers.py'))
B, CF, I = L.B, L.CF, L.I
usd = lambda v: '$' + format(round(v), ',')
DIMS = ['childcost', 'simone', 'school', 'parents', 'legacy', 'retire']
mean = lambda a: sum(a) / len(a) if a else float('nan')


def peak_and_savings(row):
    """Peak annual essential expenses, and the lowest sustained savings rate."""
    evs = (L.child_living_events(L.CHILD_ADDER[row['childcost']][1])
           + L.schooling_events(*L.SCHOOLING[row['school']][1:])
           + B.house_events(B.HOUSES[L.HOUSE][1]))
    pid = row['parents']
    if L.PARENTS[pid][1] is not None:
        _n, path, sched, med = L.PARENTS[pid]
        evs += L.care_events(path, sched, med)
    peak = {}
    for e in evs:
        if e['kind'] != 'expenseEssential':
            continue
        a = e['amount']
        amt = a.get('perYear', a.get('perMonth', 0) * 12)
        t = e['timing']
        if 'at' in t or 'calendarYear' not in t.get('from', {}):
            continue
        y1 = t['to'].get('calendarYear', 2060)
        for y in range(t['from']['calendarYear'], min(y1, 2060) + 1):
            peak[y] = peak.get(y, 0) + amt
    _nm, lvl, _tmp = L.SIMONE[row['simone']]
    low = CF.net_income(I.MICHAEL_GROSS + lvl) - B.LIVING
    return (max(peak.values()) if peak else 0), low


rows = []
for r in csv.DictReader(open(sys.argv[1])):
    r['ok'] = float(r['successProbability'])
    r['spend'] = float(r['medianRetirementSpendingPerMonth'])
    r['p5floor'] = float(r['p5SpendingFloorPerMonth'])
    pk, sav = peak_and_savings(r)
    r['peak'], r['sav'] = pk, sav
    r['feasible'] = pk <= sav
    rows.append(r)

CONDS = ['base-returns', 'pessimistic', 'severe']
base = [r for r in rows if r['condition'] == 'base-returns']
print('=' * 92)
print('FEASIBILITY CENSUS')
print('=' * 92)
nf = [r for r in base if not r['feasible']]
print(f'{len(base) - len(nf)} of {len(base)} combinations are payable out of cash flow; '
      f'{len(nf)} are not.')
if nf:
    print('\nUnpayable combinations concentrate in:')
    for d in DIMS:
        c = collections.Counter(r[d] for r in nf)
        tot = collections.Counter(r[d] for r in base)
        worst = sorted(c.items(), key=lambda kv: -kv[1] / tot[kv[0]])[:2]
        print(f'  {d:<11}' + '  '.join(
            f'{k} {v}/{tot[k]}' for k, v in worst))
    print('\nThese are excluded from the ranking below. They are not risky plans;')
    print('they are plans the household cannot fund, whatever the market does.')

print('\n' + '=' * 92)
print('MATCHED EFFECT SIZES  (mean within-stratum spread in floor-success)')
print('=' * 92)
for cond in CONDS:
    sub = [r for r in rows if r['condition'] == cond]
    res = []
    for dim in DIMS:
        others = [d for d in DIMS if d != dim]
        strata = collections.defaultdict(list)
        for r in sub:
            strata['|'.join(r[d] for d in others)].append(r)
        variants = sorted({r[dim] for r in sub})
        spreads, per = [], collections.defaultdict(list)
        for _k, grp in strata.items():
            if len(grp) != len(variants) or not all(x['feasible'] for x in grp):
                continue
            vals = [x['ok'] for x in grp]
            spreads.append(max(vals) - min(vals))
            for x in grp:
                per[x[dim]].append(x['ok'])
        res.append((mean(spreads), dim, len(spreads), per))
    res.sort(reverse=True, key=lambda t: t[0])
    print(f'\n{cond}  (strata where every variant is payable)')
    for spread, dim, n, per in res:
        print(f'  {dim:<11}{100 * spread:>7.1f} pts   ({n} strata)')
        if cond == 'severe':
            for v, vals in sorted(per.items(), key=lambda kv: -mean(kv[1])):
                print(f'      {v:<12}{100 * mean(vals):>6.1f}%')

print('\n' + '=' * 92)
print('WHAT PASS 2 SHOULD SWEEP')
print('=' * 92)
sub = [r for r in rows if r['condition'] == 'severe']
res = []
for dim in DIMS:
    others = [d for d in DIMS if d != dim]
    strata = collections.defaultdict(list)
    for r in sub:
        strata['|'.join(r[d] for d in others)].append(r)
    variants = sorted({r[dim] for r in sub})
    spreads = [max(x['ok'] for x in g) - min(x['ok'] for x in g)
               for g in strata.values()
               if len(g) == len(variants) and all(x['feasible'] for x in g)]
    res.append((mean(spreads), dim))
res.sort(reverse=True)
print('Ranked by effect on floor-success under severe returns:')
for spread, dim in res:
    keep = 'sweep in pass 2' if spread >= 0.05 else 'hold fixed'
    print(f'  {dim:<11}{100 * spread:>7.1f} pts   {keep}')
