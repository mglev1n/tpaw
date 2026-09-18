#!/usr/bin/env python3
"""Tables for the parental-support grids. Usage: analyze.py <grid.csv> <share.csv>"""
import csv, sys

def load(p):
    with open(p) as f:
        return [dict(r, spend=float(r['medianRetirementSpendingPerMonth']),
                     success=float(r['successProbability'])) for r in csv.DictReader(f)]

NAMES = {'none': 'No support needed',
         'us-healthy': 'US, stay independent',
         'us-typical': 'US, one assisted 2032, both nursing 2036',
         'us-severe': 'US, home care 2030, nursing 2033',
         'br-light': 'Brazil, home care from 2032',
         'br-heavy': 'Brazil, home care 2030, nursing 2034'}
HOUSES = {'ch-08003': 'Cherry Hill $655k', 'ml-wynnewood': 'Wynnewood $1.07M',
          'ml-brynmawr': 'Bryn Mawr $1.18M'}
usd = lambda v: '$' + format(round(v), ',')

rows = load(sys.argv[1])
print('=' * 84)
print('RETIREMENT SPENDING BY PARENTAL TRAJECTORY AND HOUSE (base returns, 50% share)')
print('=' * 84)
print(f"{'trajectory':<42}" + ''.join(f'{h:>18}' for h in HOUSES.values()))
base = {}
for sid, label in NAMES.items():
    line, cells = f'{label:<42}', {}
    for hid in HOUSES:
        r = next(x for x in rows if x['condition'] == 'base-returns'
                 and x['support'] == sid and x['house'] == hid)
        cells[hid] = r
        line += f"{usd(r['spend']) + '  ' + ('%.0f%%' % (100 * r['success'])):>18}"
    base[sid] = cells
    print(line)
print('\nEach cell is median first-year retirement spending and the plan\'s success')
print('probability. Once success falls below about 50% the median stops being')
print('meaningful -- the portfolio is exhausted and the number is a floor, not a plan.')

print('\n' + '=' * 84)
print('COST OF EACH TRAJECTORY vs NO SUPPORT, and what a cheaper house buys back')
print('=' * 84)
print(f"{'trajectory':<42}{'cost at Cherry Hill':>21}{'cost at Bryn Mawr':>20}")
for sid, label in NAMES.items():
    if sid == 'none':
        continue
    a = base['none']['ch-08003']['spend'] - base[sid]['ch-08003']['spend']
    b = base['none']['ml-brynmawr']['spend'] - base[sid]['ml-brynmawr']['spend']
    print(f'{label:<42}{usd(-a) + "/mo":>21}{usd(-b) + "/mo":>20}')
h = base['none']['ch-08003']['spend'] - base['none']['ml-brynmawr']['spend']
print(f"\nMoving from Bryn Mawr to Cherry Hill is worth {usd(h)}/mo with no support "
      f"needed.\nCompare that against each row above: the house decision only "
      f"dominates in the\nbenign trajectories.")

print('\n' + '=' * 84)
print('THE SIBLING SPLIT (base returns, Cherry Hill house)')
print('=' * 84)
srows = load(sys.argv[2])
print(f"{'trajectory':<34}{'we pay 33%':>18}{'we pay 50%':>18}{'we pay 100%':>18}")
for tid, label in (('us-severe', 'US, home care then nursing'),
                   ('br-heavy', 'Brazil, home care then nursing')):
    line = f'{label:<34}'
    for sid in ('third', 'half', 'all'):
        r = next(x for x in srows if x['condition'] == 'base-returns'
                 and x['support'] == f'{tid}-{sid}')
        line += f"{usd(r['spend']) + '  ' + ('%.0f%%' % (100 * r['success'])):>18}"
    print(line)
print('\nThe US row is not a spectrum of worse retirements. Peak support on that')
print('trajectory is $315,000 a year against $331,000 of net income, so at a 50%')
print('or 100% share the household cannot pay it out of cash flow at all -- the')
print('plan is budget-infeasible, and the spending figure is the portfolio')
print('draining rather than a lifestyle. The Brazilian row stays payable at every')
print('split, which is the whole finding.')
