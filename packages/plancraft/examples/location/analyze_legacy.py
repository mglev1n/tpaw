#!/usr/bin/env python3
"""The location decision when a real legacy is actually being funded.

Usage: analyze_legacy.py <grid-legacy.csv> <njprobe-out-dir>

Two tables. The first is the raw sweep: what each target costs in retirement
spending, by house. The second is the like-for-like one, and is the point.
The legacy target applies to the PORTFOLIO; the house sits outside it. A
household in a $1.18M house bequeaths that house without funding a dollar of
it out of savings, so at a common portfolio target the cheaper household is
leaving materially less in total. Table two equalizes TOTAL bequest by asking
each household to fund the house-price gap as extra portfolio legacy.
"""
import csv, os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('loc_build',
                                              os.path.join(HERE, 'build.py'))
loc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loc)
sys.path.insert(0, HERE)
from nj_retirement_tax import analyze as nj_analyze          # noqa: E402

LEGACY = loc.LEGACY_LEVELS
PRICE = {k: v[2] for k, v in loc.LOCATIONS.items()}
NAME = {k: v[0] for k, v in loc.LOCATIONS.items()}
usd = lambda v: '$' + format(round(v), ',')

adj = {r['loc']: r['level'] / 12 for r in nj_analyze(sys.argv[2])
       if r['sav'] == 'mid' and r['retire'] == 65}
with open(sys.argv[1]) as f:
    rows = [dict(r, spend=float(r['medianRetirementSpendingPerMonth'])
                 - adj.get(r['location'], 0.0),
                 success=float(r['successProbability'])) for r in csv.DictReader(f)]
get = lambda l, h: next(r for r in rows if r['condition'] == 'base-returns'
                        and r['legacy'] == l and r['location'] == h)

print('=' * 92)
print('REAL LEGACY TARGET vs HOUSE  (31% savings, retire 65, base returns)')
print('=' * 92)
print('All figures are real 2026 dollars. The legacy target is real; expected')
print('returns are real; the only nominal amount is mortgage P&I, which erodes.\n')
print(f"{'house':<34}{'price':>12}" + ''.join(
    f"{('no legacy' if a == 0 else '$%dM real' % (a / 1e6)):>16}"
    for a in LEGACY.values()))
for h in PRICE:
    line = f'{NAME[h][:34]:<34}{usd(PRICE[h]):>12}'
    for lid in LEGACY:
        r = get(lid, h)
        line += f"{usd(r['spend']) + ' ' + ('%.0f%%' % (100 * r['success'])):>16}"
    print(line)
print(f"\n{'cost of the target':<46}" + ''.join(
    f"{('$%dM' % (a / 1e6)):>16}" for a in LEGACY.values() if a))
for h in PRICE:
    line = f'{NAME[h][:46]:<46}'
    for lid, amt in LEGACY.items():
        if amt:
            line += f"{usd(get(lid, h)['spend'] - get('none', h)['spend']) + '/mo':>16}"
    print(line)

print('\n' + '=' * 92)
print('LIKE-FOR-LIKE: equal TOTAL bequest (house equity + portfolio legacy)')
print('=' * 92)


def interp(h, target):
    pts = sorted((amt, get(lid, h)['spend']) for lid, amt in LEGACY.items())
    if target <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if target <= x1:
            return y0 + (y1 - y0) * (target - x0) / (x1 - x0)
    # Beyond the top simulated point, extend the last segment. The cost of a
    # target is close to linear (about $1,075/mo per $1M) so this is safe over
    # the short distances involved here.
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    return y1 + (y1 - y0) * (target - x1) / (x1 - x0)


top = max(PRICE.values())
for headline in (1_000_000, 5_000_000):
    print(f'\nTotal bequest of {usd(top + headline)}: the most expensive house '
          f'({usd(top)}) plus {usd(headline)}.')
    print(f"{'house':<34}{'price':>12}{'portfolio legacy':>19}{'spending':>13}")
    for h in sorted(PRICE, key=lambda k: -PRICE[k]):
        need = top + headline - PRICE[h]
        print(f'{NAME[h][:34]:<34}{usd(PRICE[h]):>12}{usd(need):>19}'
              f'{usd(interp(h, need)) + "/mo":>13}')
print('\nLinearly extended past the simulated $5M point where the required portfolio')
print('legacy exceeds it; the cost of a target runs about $1,075/mo per $1M and is')
print('close to linear, so the extension is short and safe.')
print('House equity is valued at today\'s real price and assumes it tracks')
print('inflation and is sold. It is an illiquid, single-market bequest; a dollar')
print('of portfolio is not the same asset even when the number matches.')
