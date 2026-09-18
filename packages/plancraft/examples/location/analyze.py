#!/usr/bin/env python3
"""Main Line vs Cherry Hill: paired comparison with the NJ retirement tax
applied post hoc.

Usage: analyze.py <grid.csv> <njprobe-out-dir>

The grid is run with the NJ retirement tax set to zero, because that tax is a
step function of the portfolio draw and the draw is set jointly by three grid
dimensions. nj_retirement_tax.py measures the draw the simulation actually
produces and converts the tax stream into its level annuity equivalent; that
level amount is subtracted here from the NJ cells' sustainable spending.
"""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nj_retirement_tax import analyze as nj_analyze          # noqa: E402
from build import LOCATIONS, SAVINGS_RATES, RETIRE           # noqa: E402

grid_csv, probe_dir = sys.argv[1], sys.argv[2]
adj = {(r['loc'], r['sav'], r['retire']): r['level'] / 12 for r in nj_analyze(probe_dir)}

rows = []
with open(grid_csv) as f:
    for r in csv.DictReader(f):
        r['spend'] = float(r['medianRetirementSpendingPerMonth'])
        r['success'] = float(r['successProbability'])
        r['retire_age'] = int(r['retire'][1:])
        r['adj'] = adj.get((r['location'], r['savings'], r['retire_age']), 0.0)
        r['net'] = r['spend'] - r['adj']
        rows.append(r)

NAME = {k: v[0] for k, v in LOCATIONS.items()}
PA = [k for k, v in LOCATIONS.items() if v[1] == 'pa']

def block(cond):
    sub = [r for r in rows if r['condition'] == cond]
    print(f"\n=== {cond}: median first-year retirement lifestyle spending, $/mo ===")
    print(f"{'save':6}{'retire':>7}  " + ''.join(f"{NAME[k][:22]:>24}" for k in LOCATIONS))
    print(' ' * 15 + '(parenthesis = NJ retirement tax effect, already applied;')
    print(' ' * 15 + ' negative = tax, positive = Stay NJ/ANCHOR relief net of tax)')
    for sav in SAVINGS_RATES:
        for age in RETIRE:
            cells = {r['location']: r for r in sub
                     if r['savings'] == sav and r['retire_age'] == age}
            line = f"{sav:6}{age:>7}  "
            for k in LOCATIONS:
                c = cells[k]
                tag = f"({-c['adj']:+,.0f})" if c['adj'] else ''
                line += f"{'$' + format(c['net'], ',.0f'):>13}{tag:>11}"
            print(line)

def paired(pa_key, nj_key, title, note):
    print(f"\n=== {title} ===")
    print(note)
    print(f"{'cond':14}{'save':6}{'retire':>7}{'PA':>12}{'NJ':>13}{'NJ - PA':>10}{'%':>9}")
    for cond in ('pessimistic', 'base-returns', 'optimistic'):
        for sav in SAVINGS_RATES:
            for age in RETIRE:
                g = {r['location']: r for r in rows
                     if r['condition'] == cond and r['savings'] == sav
                     and r['retire_age'] == age}
                a, b = g[pa_key]['net'], g[nj_key]['net']
                print(f"{cond:14}{sav:6}{age:>7}{a:>12,.0f}{b:>13,.0f}"
                      f"{b - a:>+10,.0f}{100 * (b - a) / a:>+8.1f}%")

block('base-returns')
paired('ml-brynmawr', 'ch-08003',
       'SAME HOUSE: Cherry Hill 08003 $655k vs Bryn Mawr $1.18M',
       'The same 4-bedroom house, at each market\'s price. Isolates what the '
       'Main Line\n premium buys.')
paired('ml-wynnewood', 'ch-samespend',
       'SAME PRICE: $1,068,301 in Cherry Hill vs the same $1,068,301 in Wynnewood',
       'Identical housing outlay, so price cancels and only the STATE differs: '
       'property\n tax rate, income tax in both phases, auto insurance, sales tax.')


# --- Break-even Main Line price --------------------------------------------
# The whole comparison reduces to one number a buyer can act on: how much
# house on the Main Line carries the same annual cost as the Cherry Hill
# house they would otherwise buy?
from build import (pmt, DOWN_PCT, PROPERTY_TAX, INSURANCE_PCT,   # noqa: E402
                   MAINTENANCE_PCT, NJ_NET, PA_NET,
                   NJ_AUTO_INSURANCE_EXTRA, NJ_SALES_TAX_EXTRA)

NJ_WORKING_EDGE = (NJ_NET - PA_NET) - (NJ_AUTO_INSURANCE_EXTRA + NJ_SALES_TAX_EXTRA)
carry_rate = lambda st: (DOWN_PCT_COST := pmt(1 - DOWN_PCT)) + PROPERTY_TAX[st] \
    + INSURANCE_PCT + MAINTENANCE_PCT

print('\n=== Break-even Main Line price ===')
print(f"NJ banks ${NJ_WORKING_EDGE:,.0f}/yr while working (income tax credit for the "
      f"Philadelphia\n wage tax, less NJ auto insurance and sales tax).\n")
print(f"{'Cherry Hill house':>22}{'NJ annual cost':>16}{'break-even Lower Merion price':>32}")
for key in ('ch-08003', 'ch-08034'):
    price = LOCATIONS[key][2]
    nj_cost = price * carry_rate('nj') - NJ_WORKING_EDGE
    be = nj_cost / carry_rate('pa')
    print(f"{'$' + format(price, ',.0f'):>22}{'$' + format(nj_cost, ',.0f'):>16}"
          f"{'$' + format(be, ',.0f'):>32}")
print(f"\n{'Lower Merion house':>22}{'PA annual cost':>16}{'break-even Cherry Hill price':>32}")
for key in ('ml-brynmawr', 'ml-wynnewood'):
    price = LOCATIONS[key][2]
    pa_cost = price * carry_rate('pa')
    be = (pa_cost + NJ_WORKING_EDGE) / carry_rate('nj')
    print(f"{'$' + format(price, ',.0f'):>22}{'$' + format(pa_cost, ',.0f'):>16}"
          f"{'$' + format(be, ',.0f'):>32}")
print('\nAbove the break-even price the Main Line costs more per year than Cherry Hill;')
print('below it, less. Retirement-phase tax excluded -- it is within a few hundred')
print('dollars a month either way and, net of Stay NJ and ANCHOR relief, often favors NJ.')
