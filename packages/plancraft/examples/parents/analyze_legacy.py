#!/usr/bin/env python3
"""What a legacy target costs, and the like-for-like bequest comparison.

Usage: analyze_legacy.py <grid-legacy.csv>

The portfolio legacy target does not cover the house. A household in a $1.18M
house already bequeaths that house; a household in a $655k house bequeaths
$655k. Comparing the two at a common portfolio legacy of zero credits the
expensive house with a $525k bequest it never had to fund out of the
portfolio. The second table fixes that by asking each household to fund the
house-price gap as portfolio legacy, so total bequest is equal.
"""
import csv, os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'loc_build', os.path.join(os.path.dirname(HERE), 'location', 'build.py'))
loc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loc)

HOUSES = ['ch-08003', 'ch-850k', 'ch-1m', 'ml-brynmawr']
HNAME = {h: loc.LOCATIONS[h][0] for h in HOUSES}
PRICE = {h: loc.LOCATIONS[h][2] for h in HOUSES}
LEGACY = {'none': 0, 'm1': 1_000_000, 'm2_5': 2_500_000, 'm5': 5_000_000}
SUPPORT = {'none': 'No support needed',
           'us-typical': 'US, one assisted 2032, both nursing 2036',
           'br-heavy': 'Brazil, home care 2030, nursing 2034'}
usd = lambda v: '$' + format(round(v), ',')

with open(sys.argv[1]) as f:
    rows = [dict(r, spend=float(r['medianRetirementSpendingPerMonth']),
                 success=float(r['successProbability'])) for r in csv.DictReader(f)]
get = lambda l, h, s: next(
    r for r in rows if r['condition'] == 'base-returns' and r['legacy'] == l
    and r['house'] == h and r['support'] == s)

for sup, slabel in SUPPORT.items():
    print('=' * 88)
    print(f'LEGACY TARGET vs HOUSE -- {slabel}')
    print('=' * 88)
    print(f"{'portfolio legacy':<20}" + ''.join(f'{HNAME[h][:20]:>17}' for h in HOUSES))
    for lid, amt in LEGACY.items():
        line = f"{('none' if amt == 0 else usd(amt)):<20}"
        for h in HOUSES:
            r = get(lid, h, sup)
            line += f"{usd(r['spend']) + ' ' + ('%.0f%%' % (100 * r['success'])):>17}"
        print(line)
    print(f"\n{'cost of the target':<20}" + ''.join(f'{HNAME[h][:20]:>17}' for h in HOUSES))
    for lid, amt in LEGACY.items():
        if amt == 0:
            continue
        line = f"{usd(amt):<20}"
        for h in HOUSES:
            d = get(lid, h, sup)['spend'] - get('none', h, sup)['spend']
            unfundable = get(lid, h, sup)['spend'] == 0
            line += f"{(usd(d) + '/mo' + ('*' if unfundable else '')):>17}"
        print(line)
    print('* target is unfundable: lifestyle spending is driven to zero and the')
    print('  figure is the whole of it, not the marginal cost of the target.')
    print()

print('=' * 88)
print('LIKE-FOR-LIKE: equal TOTAL bequest (house equity + portfolio legacy)')
print('=' * 88)
print('The house is outside the portfolio, so it is a bequest the expensive')
print('household never funds out of savings. Here every household leaves the same')
print('total, by asking the cheaper ones to fund the house-price gap as portfolio')
print('legacy. Interpolated between the simulated legacy levels.\n')


def interp(h, sup, target):
    pts = sorted((LEGACY[l], get(l, h, sup)['spend']) for l in LEGACY)
    if target <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if target <= x1:
            return y0 + (y1 - y0) * (target - x0) / (x1 - x0)
    return pts[-1][1]


top = max(PRICE[h] for h in HOUSES)
for sup, slabel in SUPPORT.items():
    print(f'{slabel}')
    print(f"{'house':<26}{'price':>12}{'portfolio legacy':>19}{'total bequest':>16}"
          f"{'spending':>12}")
    for h in HOUSES:
        gap = top - PRICE[h]
        print(f'{HNAME[h][:26]:<26}{usd(PRICE[h]):>12}{usd(gap):>19}'
              f'{usd(top):>16}{usd(interp(h, sup, gap)) + "/mo":>12}')
    print()
print('Bequest here is the house at today\'s real price plus the portfolio target;')
print('it ignores PA inheritance tax (4.5% to children) against NJ (0% to Class A),')
print('which is unmodeled and would favor the New Jersey rows.')
