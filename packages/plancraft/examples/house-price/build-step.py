#!/usr/bin/env python3
"""House price at $525-575k gross, with the second earner stepping up mid-2028.

The engine models one portfolio and takes NET CONTRIBUTIONS, which means income
only reaches the simulation through savings. Income level and savings rate are
therefore combined into a single dimension -- varying them separately would let
the grid claim a raise that never shows up anywhere.

Phase 1 (now -> Jun 2028): one attending plus one fellow.
Phase 2 (Jul 2028 on):     both attending, $525k or $575k gross.
"""
import collections, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR, BUY_YEAR, STEP_YEAR, STEP_MONTH = 2026, 2027, 2028, 7
CURRENT_AGE, MAX_AGE = 37, 95
PORTFOLIO_NOW = 400_000          # invested, excluding down-payment cash
PHASE1_SAVINGS = 110_000         # ~18 months only, so it barely moves the answer

# Net of federal, PA and payroll tax for MFJ with two earners above the wage base.
NET = {525_000: 364_000, 575_000: 394_000}
RATES = collections.OrderedDict([('hi', 0.42), ('mid', 0.33), ('lo', 0.24)])

DOWN_PCT, RATE, YRS = 0.20, 0.065, 30
TAX, INS, MAINT = 0.016, 0.004, 0.010
HOUSES = collections.OrderedDict([('h700', 700_000), ('h900', 900_000), ('h1000', 1_000_000)])
RETIRE = [55, 60, 65]
SS = {55: (3700, 3300), 60: (4100, 3600), 65: (4500, 3900)}

def pmt(P):
    r = RATE / 12; n = YRS * 12
    return P * r / (1 - (1 + r) ** -n) * 12

def event(i, label, kind, amount, timing, nominal=False):
    e = collections.OrderedDict([('id', i), ('label', label), ('kind', kind), ('amount', amount)])
    if nominal: e['nominal'] = True
    e['timing'] = timing
    return e

MAX_DOWN = max(HOUSES.values()) * DOWN_PCT

base = collections.OrderedDict([
    ('plancraft', 1),
    ('meta', {'name': 'House price with a mid-2028 income step',
              'description': ('Two 37-year-olds, no debt. One attending plus one fellow until '
                              'Jun 2028, then both attending at $525k or $575k gross. $400,000 '
                              'invested plus down-payment cash. Real 2026 dollars, net of tax.'),
              'anchorYear': ANCHOR}),
    ('household', {'person1': {'currentAge': {'years': CURRENT_AGE}, 'retirementAge': {'years': 65},
                               'maxAge': {'years': MAX_AGE}},
                   'person2': {'currentAge': {'years': CURRENT_AGE}, 'retirementAge': {'years': 65},
                               'maxAge': {'years': MAX_AGE}},
                   'withdrawalStart': 'person1'}),
    ('portfolio', {'balance': PORTFOLIO_NOW + MAX_DOWN}),
    ('events', [event('save-phase1', 'Savings (one attending, one fellow)', 'savings',
                      {'perYear': PHASE1_SAVINGS},
                      {'from': {'named': 'now'},
                       'to': {'calendarYear': STEP_YEAR, 'month': STEP_MONTH - 1}})]),
    ('simulation', {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}},
                    'inflation': {'manual': 0.024},
                    'sampling': {'type': 'monteCarlo', 'numRuns': 2000, 'seed': 1776},
                    'legacy': 0}),
])

def house_variants():
    out = []
    for vid, price in HOUSES.items():
        down = price * DOWN_PCT
        out.append(collections.OrderedDict([
            ('id', vid), ('name', f'${price//1000}k house'),
            ('events', [
                event('house-down', 'Down payment (20%)', 'expenseEssential',
                      {'oneTime': round(down)}, {'at': {'calendarYear': BUY_YEAR, 'month': 6}}),
                event('house-pi', 'Mortgage principal and interest', 'expenseEssential',
                      {'perYear': round(pmt(price - down))},
                      {'from': {'calendarYear': BUY_YEAR, 'month': 1},
                       'to': {'calendarYear': BUY_YEAR + YRS - 1, 'month': 12}}, nominal=True),
                event('house-carry', 'Property tax, insurance, maintenance', 'expenseEssential',
                      {'perYear': round(price * (TAX + INS + MAINT))},
                      {'from': {'calendarYear': BUY_YEAR, 'month': 1},
                       'to': {'named': 'maxAge', 'person': 'person1'}}),
            ]),
        ]))
    return out

def income_variants():
    out = []
    for gross, netinc in NET.items():
        for rid, rate in RATES.items():
            amt = int(round(netinc * rate, -3))
            out.append(collections.OrderedDict([
                ('id', f'g{gross//1000}-{rid}'),
                ('name', f'${gross//1000}k gross, save ${amt//1000}k'),
                ('events', [event('save-phase2', 'Savings (both attending)', 'savings',
                                  {'perYear': amt},
                                  {'from': {'calendarYear': STEP_YEAR, 'month': STEP_MONTH},
                                   'to': {'named': 'lastWorkingMonth', 'person': 'person1'}})]),
            ]))
    return out

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'House price at $525-575k gross with a 2028 income step'),
    ('description', (
        'Two 37-year-olds, no student debt, $400,000 invested plus down-payment cash. One '
        'attending plus one fellow saving $110,000/yr until Jun 2028, then both attending at '
        '$525,000 or $575,000 gross (~$364,000 and ~$394,000 net of federal, PA and payroll '
        'tax for a married couple with two earners above the Social Security wage base). '
        'Income and savings rate are one dimension because the engine takes net contributions '
        '-- income reaches the simulation only through savings, so varying them separately '
        'would credit a raise that never appears. House bought 2027, 20% down, 30-year fixed '
        'at 6.5%; property tax 1.6%, insurance 0.4%, maintenance 1.0% of value. Principal and '
        'interest is NOMINAL and erodes in real terms; tax, insurance and maintenance are real '
        'and continue for life. All variants start from the same balance sheet so the cheaper '
        'house is not credited twice. Metric is median first-year general (lifestyle) '
        'retirement spending, which excludes the housing costs themselves. Home equity is not '
        'counted in the portfolio.'
    )),
    ('base', 'base-step.scenario.json'),
    ('dimensions', [
        {'id': 'house', 'name': 'House price', 'variants': house_variants()},
        {'id': 'income', 'name': 'Income and savings rate', 'variants': income_variants()},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', [
                    event('ss-1', 'Social Security (person 1, at 70)', 'retirementIncome',
                          {'perMonth': SS[a][0]},
                          {'from': {'age': {'person': 'person1', 'years': 70}},
                           'to': {'named': 'maxAge', 'person': 'person1'}}),
                    event('ss-2', 'Social Security (person 2, at 70)', 'retirementIncome',
                          {'perMonth': SS[a][1]},
                          {'from': {'age': {'person': 'person2', 'years': 70}},
                           'to': {'named': 'maxAge', 'person': 'person2'}}),
                ]),
            ]) for a in RETIRE]},
    ]),
    ('conditions', [
        {'id': 'pessimistic', 'name': 'Pessimistic (3.5%/1.5%)',
         'simulation': {'expectedReturns': {'fixed': {'stocks': 0.035, 'bonds': 0.015}}}},
        {'id': 'base-returns', 'name': 'Base (5%/2%)',
         'simulation': {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}}}},
        {'id': 'optimistic', 'name': 'Optimistic (6.5%/3%)',
         'simulation': {'expectedReturns': {'fixed': {'stocks': 0.065, 'bonds': 0.03}}}},
    ]),
])

for name, obj in [('base-step.scenario.json', base), ('grid-step.json', grid)]:
    with open(os.path.join(HERE, name), 'w') as f:
        json.dump(obj, f, indent=2); f.write('\n')

print('income variants:')
for gross, netinc in NET.items():
    for rid, rate in RATES.items():
        amt = int(round(netinc * rate, -3))
        print(f"  ${gross//1000}k gross -> net ${netinc:,} | save ${amt:,} "
              f"| consume ${netinc-amt:,}")
print('\nhouse annual cost (year 1):')
for vid, price in HOUSES.items():
    down = price * DOWN_PCT
    print(f"  ${price//1000}k: P&I ${pmt(price-down):>8,.0f} (nominal) + carry "
          f"${price*(TAX+INS+MAINT):>7,.0f} (real) = ${pmt(price-down)+price*(TAX+INS+MAINT):>8,.0f}")
n = len(HOUSES)*len(NET)*len(RATES)*len(RETIRE)
print(f"\ndescription chars: {len(grid['description'])}")
print(f"combos: {n} x 3 conditions = {n*3} sims")
