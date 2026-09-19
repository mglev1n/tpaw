#!/usr/bin/env python3
"""Where the plan breaks. Usage: analyze_stress.py <grid-stress.csv> [recovery.csv]

With a spending floor set, successProbability finally means something:
"given that we refuse to live on less than the floor, how likely is that
refusal to be affordable". Anything under about 90% is a plan that expects
to need one of the recovery levers.
"""
import csv, sys

rows = [dict(r, spend=float(r['medianRetirementSpendingPerMonth']),
             p5=float(r['p5RetirementSpendingPerMonth']),
             floorv=float(r['p5SpendingFloorPerMonth']),
             ok=float(r['successProbability']))
        for r in csv.DictReader(open(sys.argv[1]))]
usd = lambda v: '$' + format(round(v), ',')
g = lambda c, s, f, r: next(x for x in rows if x['condition'] == c
                            and x['stress'] == s and x['floor'] == f
                            and x['retire'] == r)

STRESS = [('base', 'As planned'), ('private', 'Private school'),
          ('creep', 'Creep to $12k/mo'), ('simone', 'Simone 0.6 FTE'),
          ('long', 'Both live to 100'), ('care', 'US nursing, we pay all'),
          ('creep-simone', 'Creep + Simone 0.6'), ('all', 'Everything at once')]
COND = [('base-returns', 'Base'), ('pessimistic', 'Pessimistic'),
        ('severe', 'Severe 2%/0.5%')]


def pct(v):
    s = f'{100 * v:.0f}%'
    return s if v >= 0.90 else (s + ' !' if v >= 0.75 else s + ' !!')


print('=' * 96)
print('CAN WE HOLD A $12,000/MO COMFORT FLOOR?  (success = the floor stayed affordable)')
print('=' * 96)
for rid, age in (('r55', 55), ('r60', 60), ('r65', 65)):
    print(f'\nRetire at {age}')
    print(f"{'what goes wrong':<26}" + ''.join(f'{n:>18}' for _c, n in COND))
    for sid, sname in STRESS:
        line = f'{sname:<26}'
        for cid, _n in COND:
            line += f'{pct(g(cid, sid, "f12", rid)["ok"]):>18}'
        print(line)
print('\n!  below 90%   !!  below 75%')

print('\n' + '=' * 96)
print('HOW HIGH A FLOOR SURVIVES?  (retire 60, by stressor and condition)')
print('=' * 96)
print(f"{'what goes wrong':<26}{'condition':<16}" +
      ''.join(f'{f"${k}k floor":>13}' for k in (8, 12, 16)))
for sid, sname in STRESS:
    for ci, (cid, cname) in enumerate(COND):
        line = f'{sname if ci == 0 else "":<26}{cname:<16}'
        for fid in ('f8', 'f12', 'f16'):
            line += f'{pct(g(cid, sid, fid, "r60")["ok"]):>13}'
        print(line)
    print()

print('=' * 96)
print('HOW MUCH LIFESTYLE CREEP IS AFFORDABLE?')
print('=' * 96)
print('The question underneath "spend responsibly": at what point does raising')
print('present-day spending put the retirement floor at risk?\n')
print(f"{'living costs now':<22}{'retire 60, pess.':>20}{'retire 60, severe':>20}"
      f"{'retire 65, severe':>20}")
for sid, label in (('base', '$8,000/mo'), ('creep', '$12,000/mo')):
    print(f'{label:<22}'
          f'{pct(g("pessimistic", sid, "f12", "r60")["ok"]):>20}'
          f'{pct(g("severe", sid, "f12", "r60")["ok"]):>20}'
          f'{pct(g("severe", sid, "f12", "r65")["ok"]):>20}')

if len(sys.argv) > 2:
    rec = [dict(r, spend=float(r['medianRetirementSpendingPerMonth']),
                ok=float(r['successProbability']))
           for r in csv.DictReader(open(sys.argv[2]))]
    LEVERS = [('none', 'Nothing changes'), ('work-63', 'Work to 63'),
              ('work-65', 'Work to 65'), ('downsize', 'Buy the $655k house'),
              ('public', 'Public school instead of private'),
              ('hold-line', 'Hold living costs at $8,000/mo'),
              ('share-33', "Sister carries two thirds"),
              ('lower-floor', 'Accept an $8,000/mo floor')]
    base = {c: next(x for x in rec if x['condition'] == c and x['lever'] == 'none')
            for c, _n in COND}
    print('\n' + '=' * 96)
    print('THE RECOVERY LEVERS, RANKED  (one at a time, from a strained but payable plan)')
    print('=' * 96)
    print('Crept to $12k/mo, Simone 0.6 FTE, private school, both to 100,')
    print('Brazilian care split evenly, retire 60, $12,000/mo floor.\n')
    print(f"{'lever':<38}" + ''.join(f'{n:>17}' for _c, n in COND) + f"{'gain':>9}")
    scored = []
    for lid, lname in LEVERS:
        cells = {c: next(x for x in rec if x['condition'] == c and x['lever'] == lid)
                 for c, _n in COND}
        gain = cells['severe']['ok'] - base['severe']['ok']
        scored.append((gain, lid, lname, cells))
    for gain, lid, lname, cells in (
            [scored[0]] + sorted(scored[1:], key=lambda t: -t[0])):
        g2 = '' if lid == 'none' else f'{100 * gain:+.0f} pts'
        print(f'{lname:<38}' + ''.join(f'{pct(cells[c]["ok"]):>17}' for c, _n in COND)
              + f'{g2:>9}')
    print('\nGain is against "nothing changes" under the severe condition, where the')
    print('levers have room to matter. Ranked by that column.')
