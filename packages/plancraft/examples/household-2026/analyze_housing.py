#!/usr/bin/env python3
"""What the house costs, in promised floor. Usage: analyze_housing.py <csv>"""
import collections, csv, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _load('housing', os.path.join(HERE, 'housing.py'))
FLOORS, TARGET = H.P2.FLOORS, 0.90
DIMS = ['housing', 'retire', 'simone', 'parents']
usd = lambda v: '$' + format(round(v), ',')
mean = lambda a: sum(a) / len(a) if a else float('nan')

rows = list(csv.DictReader(open(sys.argv[1])))
by = collections.defaultdict(dict)
for r in rows:
    by[(r['condition'],) + tuple(r[d] for d in DIMS)][
        int(r['floor'][1:]) * 1000] = float(r['successProbability'])


def solve(curve):
    pts = sorted(curve.items())
    if pts[0][1] < TARGET:
        return max(curve.values()), 'ceiling'
    if pts[-1][1] >= TARGET:
        return None, 'above'
    for (f0, s0), (f1, s1) in zip(pts, pts[1:]):
        if s1 < TARGET <= s0:
            return (f0 if s0 == s1 else
                    f0 + (f1 - f0) * (s0 - TARGET) / (s0 - s1)), 'ok'
    return max(curve.values()), 'ceiling'


solved = {k: solve(c) for k, c in by.items()}
fmt = lambda v: (usd(v[0]) if v[1] == 'ok'
                 else ('>' + usd(FLOORS[-1]) if v[1] == 'above'
                       else f'fails {100 * (1 - v[0]):.0f}%'))
NAMES = {h[0]: h[1] for h in H.HOUSING}
ORDER = [h[0] for h in H.HOUSING]
PAR = [('none', 'No support'), ('br50', 'Brazil, half'), ('us50', 'US, half')]

print('=' * 96)
print('HIGHEST FLOOR AT 90% CONFIDENCE, BY HOUSE AND FINANCING  (severe returns)')
print('=' * 96)
print('Simone full time, public K-12 + in-state college, no legacy.')
print('')
print('A dollar figure is the floor you could promise yourself and keep 90% of the')
print('time. "fails N%" means NO floor reaches 90%: even promising $4,000 a month,')
print('the plan still runs out of money N% of the time. Lifestyle spending is not')
print('what breaks those cells -- the house, college and the parents are.\n')
print(f"{'':<32}" + ''.join(f'{"retire " + str(a):>17}' for a in (55, 60, 65)))
for pid, pname in PAR:
    print(f'\n{pname}')
    for hid in ORDER:
        line = f'  {NAMES[hid]:<30}'
        for a in (55, 60, 65):
            line += f"{fmt(solved[('severe', hid, f'r{a}', 'full', pid)]):>17}"
        print(line)

print('\n' + '=' * 96)
print('EACH HOUSING CHANGE, PRICED  (mean across every on-scale pair)')
print('=' * 96)
print('Against the $850k / 30yr 6.5% / 20% baseline. Negative is floor given up.\n')
print(f"{'change':<34}{'yr-1 cash':>12}{'severe':>12}{'pessimistic':>14}{'base':>11}")
cash = {}
for hid, name, price, rate, term, down in H.HOUSING:
    cash[hid] = H.pmt(price * (1 - down), rate, term) + H.carry(price)
for hid in ORDER:
    if hid == 'base':
        continue
    cells = []
    for cond in ('severe', 'pessimistic', 'base-returns'):
        d = []
        for key, val in solved.items():
            if key[0] != cond or key[1] != 'base' or val[1] != 'ok':
                continue
            o = solved.get((key[0], hid) + key[2:])
            if o and o[1] == 'ok':
                d.append(o[0] - val[0])
        cells.append(usd(mean(d)) + '/mo' if d else 'n/a')
    print(f'{NAMES[hid]:<34}{usd(cash[hid] - cash["base"]):>12}'
          f'{cells[0]:>12}{cells[1]:>14}{cells[2]:>11}')

print('\n' + '=' * 96)
print('DOLLAR OF ANNUAL HOUSING COST -> DOLLAR OF MONTHLY FLOOR')
print('=' * 96)
print('How efficiently each change converts. A change that costs more per year')
print('but less floor is the better way to spend on housing.\n')
print(f"{'change':<34}{'extra cash/yr':>15}{'floor/mo':>11}{'per $10k/yr':>14}")
for hid in ORDER:
    if hid == 'base':
        continue
    d = []
    for key, val in solved.items():
        if key[0] != 'severe' or key[1] != 'base' or val[1] != 'ok':
            continue
        o = solved.get((key[0], hid) + key[2:])
        if o and o[1] == 'ok':
            d.append(o[0] - val[0])
    dc = cash[hid] - cash['base']
    if d and abs(dc) > 100:
        print(f'{NAMES[hid]:<34}{usd(dc):>15}{usd(mean(d)):>11}'
              f'{usd(mean(d) / (dc / 10_000)):>14}')
