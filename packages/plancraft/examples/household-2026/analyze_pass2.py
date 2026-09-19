#!/usr/bin/env python3
"""Pass 2 analysis: the highest floor each choice can promise.

Usage: analyze_pass2.py <grid-pass2.csv>

For each combination of the five decision dimensions, success is measured at
six floors. Success falls as the floor rises, so the answer is where that
curve crosses 90%, found by linear interpolation between the bracketing rungs.
Below the bottom rung and above the top one the answer is reported as an
inequality rather than extrapolated, since the curve is not linear far from
the crossing.
"""
import collections, csv, sys

FLOORS = [4_000, 6_000, 8_000, 12_000, 16_000, 20_000, 24_000, 28_000]
TARGET = 0.90
DIMS = ['retire', 'simone', 'school', 'parents', 'legacy']
usd = lambda v: '$' + format(round(v), ',')
mean = lambda a: sum(a) / len(a) if a else float('nan')

rows = list(csv.DictReader(open(sys.argv[1])))
by = collections.defaultdict(dict)
for r in rows:
    key = (r['condition'],) + tuple(r[d] for d in DIMS)
    by[key][int(r['floor'][1:]) * 1000] = float(r['successProbability'])


def max_floor(curve):
    """Highest floor sustained at TARGET confidence. None means off-scale."""
    pts = sorted(curve.items())
    if pts[0][1] < TARGET:
        return None, 'below'
    if pts[-1][1] >= TARGET:
        return None, 'above'
    for (f0, s0), (f1, s1) in zip(pts, pts[1:]):
        if s1 < TARGET <= s0:
            if s0 == s1:
                return f0, 'ok'
            return f0 + (f1 - f0) * (s0 - TARGET) / (s0 - s1), 'ok'
    return None, 'below'


solved = {}
for key, curve in by.items():
    solved[key] = max_floor(curve)

fmt = lambda v: (usd(v[0]) if v[1] == 'ok'
                 else ('>' + usd(FLOORS[-1]) if v[1] == 'above'
                       else '<' + usd(FLOORS[0])))
CONDS = [('base-returns', 'Base'), ('pessimistic', 'Pessimistic'),
         ('severe', 'Severe')]
SIMONE = [('full', 'Simone full time'), ('p50p', '0.5 FTE permanent'),
          ('homet', 'Stay-at-home, returns 2041'), ('homep', 'Stay-at-home permanent')]
SCHOOL = [('pub-pub', 'Public K-12, in-state college'),
          ('pub-priv', 'Public K-12, private college'),
          ('priv-pub', 'Private K-12, in-state college'),
          ('priv-priv', 'Private K-12, private college')]
PARENTS = [('none', 'No support'), ('br50', 'Brazil, half'),
           ('us50', 'US, half'), ('us100', 'US, all of it')]

print('=' * 94)
print(f'HIGHEST FLOOR SUSTAINED AT {TARGET:.0%} CONFIDENCE  ($/mo, real)')
print('=' * 94)
print('Public K-12 + in-state college, no legacy, severe returns unless stated.\n')
print(f"{'':<30}" + ''.join(f'{n:>16}' for _p, n in PARENTS))
for rid, age in (('r55', 55), ('r60', 60), ('r65', 65)):
    print(f'\nRetire at {age}')
    for sid, sname in SIMONE:
        line = f'  {sname:<28}'
        for pid, _n in PARENTS:
            line += f"{fmt(solved[('severe', rid, sid, 'pub-pub', pid, 'none')]):>16}"
        print(line)

print('\n' + '=' * 94)
print('WHAT EACH LEVER COSTS, IN DOLLARS OF PROMISED FLOOR')
print('=' * 94)
print('Mean change across every combination where both sides are on-scale,')
print('severe returns. A negative number is floor given up.\n')
for dim, pairs in (
        ('retire', [('r60', 'r55'), ('r65', 'r60')]),
        ('simone', [('full', 'p50p'), ('full', 'homet'), ('full', 'homep'),
                    ('homet', 'homep')]),
        ('school', [('pub-pub', 'pub-priv'), ('pub-pub', 'priv-pub'),
                    ('pub-pub', 'priv-priv')]),
        ('parents', [('none', 'br50'), ('none', 'us50'), ('us50', 'us100')]),
        ('legacy', [('none', 'm5')])):
    for a, b in pairs:
        deltas = []
        for key, val in solved.items():
            if key[0] != 'severe' or key[1 + DIMS.index(dim)] != a or val[1] != 'ok':
                continue
            other = list(key)
            other[1 + DIMS.index(dim)] = b
            o = solved.get(tuple(other))
            if o and o[1] == 'ok':
                deltas.append(o[0] - val[0])
        if deltas:
            print(f'  {dim:<9}{a:>11} -> {b:<11}{usd(mean(deltas)) + "/mo":>13}'
                  f'   ({len(deltas)} pairs)')

print('\n' + '=' * 94)
print('THE LEGACY: A COMPLEMENT TO THE FLOOR, NOT A COMPETITOR FOR IT')
print('=' * 94)
print('I predicted this metric would show a legacy COSTING promised floor, since a')
print('bequest has to be funded before spending. It does not, and the reasoning was')
print('wrong. A legacy target suppresses discretionary spending ABOVE the floor,')
print('which preserves the portfolio, which makes a HIGHER floor sustainable.')
print('Switching metrics could never have fixed this: both ask about the floor, and')
print('nothing that suppresses upside spending looks bad to either.')
print('')
print('The legacy is not free. It is paid in median spending, not in floor --')
print('so both halves of the trade have to be shown together:')
print('')
spend = collections.defaultdict(dict)
for r in rows:
    k = (r['condition'],) + tuple(r[d] for d in DIMS[:-1]) + (r['floor'],)
    spend[k][r['legacy']] = float(r['medianRetirementSpendingPerMonth'])
for cid, cname in CONDS:
    df, ds = [], []
    for key, val in solved.items():
        if key[0] != cid or key[-1] != 'none' or val[1] != 'ok':
            continue
        o = solved.get(key[:-1] + ('m5',))
        if o and o[1] == 'ok':
            df.append(o[0] - val[0])
    for k, v in spend.items():
        if k[0] == cid and 'none' in v and 'm5' in v:
            ds.append(v['m5'] - v['none'])
    if df and ds:
        print(f'  {cname:<13}promised floor {usd(mean(df)) + "/mo":>10}   '
              f'median spending {usd(mean(ds)) + "/mo":>10}')

print('\n' + '=' * 94)
print('A $12,000 FLOOR: WHAT COMBINATIONS CLEAR IT')
print('=' * 94)
for cid, cname in CONDS:
    ok = sum(1 for k, v in solved.items()
             if k[0] == cid and (v[1] == 'above' or (v[1] == 'ok' and v[0] >= 12_000)))
    tot = sum(1 for k in solved if k[0] == cid)
    print(f'  {cname:<14}{ok:>5} of {tot} combinations')
