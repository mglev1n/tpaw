#!/usr/bin/env python3
"""Tables for the household-2026 grids. Usage: analyze.py <grid.csv> <fers.csv>

Reports the MEDIAN and the 5th-percentile spending path side by side. They
answer different questions and the second is the one that constrains a
decision: TPAW re-amortizes every month, so a bad return sequence shows up as
spending that declines rather than as a plan that fails, and success
probability saturates at 100% in a well-funded plan.

Percentile and condition are also different uncertainties. A condition is a
different world -- we do not know the true expected return. A percentile is a
bad draw within one world. They compound, so the honest worst case is the 5th
percentile UNDER the pessimistic condition, which is what the last table
shows.
"""
import csv, sys

load = lambda p: [dict(r, spend=float(r['medianRetirementSpendingPerMonth']),
                       p5=float(r['p5RetirementSpendingPerMonth']),
                       floor=float(r['p5SpendingFloorPerMonth']),
                       success=float(r['successProbability']))
                  for r in csv.DictReader(open(p))]
usd = lambda v: '$' + format(round(v), ',')

HOUSE = {'ch-655k': '$655k', 'ch-850k': '$850k', 'ch-1m': '$1.0M'}
SCHOOL = {'none': 'No children', 'public': '2 kids, public',
          'private': '2 kids, private'}
PARENTS = {'none': 'No support', 'brazil': 'Brazil care', 'us': 'US care'}
RETIRE = {'r55': 55, 'r60': 60, 'r65': 65}

rows = load(sys.argv[1])
def g(cond, h, s, p, r, l):
    return next(x for x in rows if x['condition'] == cond and x['house'] == h
                and x['school'] == s and x['parents'] == p
                and x['retire'] == r and x['legacy'] == l)

print('=' * 94)
print('RETIREMENT AGE IS THE DIMENSION  ($850k house, 2 kids public, base returns)')
print('=' * 94)
print(f"{'':<26}" + ''.join(f'{"retire " + str(a):>21}' for a in RETIRE.values()))
for lid, lname in (('none', 'No legacy'), ('m5', 'Leave $5M real')):
    for pid, pname in PARENTS.items():
        line = f'{lname + ", " + pname:<26}'
        for r in RETIRE:
            x = g('base-returns', 'ch-850k', 'public', pid, r, lid)
            line += f'{usd(x["spend"]) + "  p5 " + usd(x["p5"]):>21}'
        print(line)
    print()

print('=' * 94)
print('WHAT A $5M REAL LEGACY COSTS')
print('=' * 94)
print(f"{'':<26}" + ''.join(f'{"retire " + str(a):>21}' for a in RETIRE.values()))
for pid, pname in PARENTS.items():
    line = f'{pname:<26}'
    for r in RETIRE:
        a = g('base-returns', 'ch-850k', 'public', pid, r, 'none')['spend']
        b = g('base-returns', 'ch-850k', 'public', pid, r, 'm5')['spend']
        line += f'{usd(b - a) + "/mo":>21}'
    print(line)

print('\n' + '=' * 94)
print('MEDIAN vs 5th PERCENTILE vs THE FLOOR  (retire 60, $5M legacy, base returns)')
print('=' * 94)
print(f"{'':<34}{'median':>12}{'p5 at 60':>12}{'p5 floor':>12}{'success':>10}")
for hid, hname in HOUSE.items():
    for sid, sname in SCHOOL.items():
        x = g('base-returns', hid, sid, 'us', 'r60', 'm5')
        print(f'{hname + ", " + sname + ", US care":<34}{usd(x["spend"]):>12}'
              f'{usd(x["p5"]):>12}{usd(x["floor"]):>12}'
              f'{100 * x["success"]:>9.0f}%')
print('\np5 floor is the lowest 5th-percentile monthly spending at any point after')
print('retirement. For TPAW that arrives late: a bad sequence grinds spending down')
print('rather than ending the plan, which is why success stays at 100%.')

print('\n' + '=' * 94)
print('THE ACTUAL WORST CASE: 5th percentile UNDER the pessimistic condition')
print('=' * 94)
print('$1.0M house, two children in private school, US parental care, $5M legacy.\n')
print(f"{'':<16}{'base p50':>13}{'base p5':>12}{'pess p50':>12}{'pess p5':>12}"
      f"{'pess floor':>13}")
for r, age in RETIRE.items():
    b = g('base-returns', 'ch-1m', 'private', 'us', r, 'm5')
    p = g('pessimistic', 'ch-1m', 'private', 'us', r, 'm5')
    print(f'{"retire " + str(age):<16}{usd(b["spend"]):>13}{usd(b["p5"]):>12}'
          f'{usd(p["spend"]):>12}{usd(p["p5"]):>12}{usd(p["floor"]):>13}')
print('\nThe gap between "base p50" and "pess p5" is the whole planning margin:')
print('one column is a good draw in a good world, the other a bad draw in a bad one.')
