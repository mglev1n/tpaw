#!/usr/bin/env python3
"""House price question: $400k gross, dual earner, no debt.

What does a $700k vs $900k vs $1.0M house cost in retirement living standard?

A house is not one number. Each price carries a down payment (out of the
portfolio, today), a NOMINAL mortgage payment (fixed in dollars, so it shrinks
in real terms over 30 years), and REAL carrying costs that do not shrink --
property tax, insurance, maintenance. Modeling the whole payment as a flat real
expense would badly overstate the cost; modeling only P&I would badly
understate it. Both are separated here.
"""
import collections, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = 2026
BUY_YEAR = 2027

# --- Household --------------------------------------------------------------
# $400,000 gross, two earners, no debt. Federal + PA state + payroll on a
# married-filing-jointly $400k is roughly $108k all-in, so ~$292,000 net.
NET_INCOME = 292_000
PORTFOLIO_NOW = 400_000        # stated separately from the down payment below
CURRENT_AGE = 37
MAX_AGE = 95

# --- House economics --------------------------------------------------------
DOWN_PCT = 0.20
MORTGAGE_RATE = 0.065
MORTGAGE_YEARS = 30
PROPERTY_TAX_PCT = 0.016       # PA suburban effective rate
INSURANCE_PCT = 0.004
MAINTENANCE_PCT = 0.010

HOUSES = collections.OrderedDict([
    ('h700', 700_000),
    ('h900', 900_000),
    ('h1000', 1_000_000),
])

def mortgage_payment(principal):
    r = MORTGAGE_RATE / 12
    n = MORTGAGE_YEARS * 12
    return principal * r / (1 - (1 + r) ** -n) * 12

def house_numbers(price):
    down = price * DOWN_PCT
    principal = price - down
    pi = mortgage_payment(principal)
    carry = price * (PROPERTY_TAX_PCT + INSURANCE_PCT + MAINTENANCE_PCT)
    return dict(price=price, down=down, principal=principal, pi=pi, carry=carry)

SAVINGS = collections.OrderedDict([
    ('save120', ('Save $120k/yr', 120_000)),
    ('save95',  ('Save $95k/yr',  95_000)),
    ('save70',  ('Save $70k/yr',  70_000)),
])
RETIRE = [55, 60, 65]
SS = {55: (3500, 3100), 60: (3900, 3400), 65: (4300, 3700)}

def event(i, label, kind, amount, timing, nominal=False):
    e = collections.OrderedDict([('id', i), ('label', label), ('kind', kind),
                                 ('amount', amount)])
    if nominal:
        e['nominal'] = True
    e['timing'] = timing
    return e

def span(a, b):
    return {'from': {'calendarYear': a, 'month': 1},
            'to': {'calendarYear': b, 'month': 12}}

base = collections.OrderedDict([
    ('plancraft', 1),
    ('meta', {'name': 'House price question: $400k gross, dual earner, no debt',
              'description': ('Two 37-year-olds, $400,000 gross (~$292,000 net), no debt, '
                              '$400,000 invested plus the down payment held in cash. House '
                              'bought 2027 with 20% down on a 30-year fixed at 6.5%. Real '
                              '2026 dollars, net of tax.'),
              'anchorYear': ANCHOR}),
    ('household', {'person1': {'currentAge': {'years': CURRENT_AGE},
                               'retirementAge': {'years': 65},
                               'maxAge': {'years': MAX_AGE}},
                   'person2': {'currentAge': {'years': CURRENT_AGE},
                               'retirementAge': {'years': 65},
                               'maxAge': {'years': MAX_AGE}},
                   'withdrawalStart': 'person1'}),
    ('portfolio', {'balance': PORTFOLIO_NOW}),
    ('events', []),
    ('simulation', {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}},
                    'inflation': {'manual': 0.024},
                    'sampling': {'type': 'monteCarlo', 'numRuns': 2000, 'seed': 1776},
                    'legacy': 0}),
])

def house_variants():
    out = []
    for vid, price in HOUSES.items():
        n = house_numbers(price)
        out.append(collections.OrderedDict([
            ('id', vid), ('name', f'${price//1000}k house'),
            # The down payment is added to the starting portfolio for every
            # variant (so all three start from the same balance sheet) and then
            # spent at purchase -- otherwise the cheaper house would be
            # rewarded twice, once for a smaller down payment and once for a
            # smaller starting portfolio.
            ('portfolio', {'balance': PORTFOLIO_NOW + max(h['down'] for h in
                           (house_numbers(p) for p in HOUSES.values()))}),
            ('events', [
                event('house-down', 'Down payment (20%)', 'expenseEssential',
                      {'oneTime': round(n['down'])},
                      {'at': {'calendarYear': BUY_YEAR, 'month': 6}}),
                # Fixed in dollars, so it erodes in real terms across 30 years.
                event('house-pi', 'Mortgage principal and interest', 'expenseEssential',
                      {'perYear': round(n['pi'])},
                      span(BUY_YEAR, BUY_YEAR + MORTGAGE_YEARS - 1), nominal=True),
                # Scale with the house and with inflation, so they stay real.
                event('house-carry', 'Property tax, insurance, maintenance',
                      'expenseEssential', {'perYear': round(n['carry'])},
                      {'from': {'calendarYear': BUY_YEAR, 'month': 1},
                       'to': {'named': 'maxAge', 'person': 'person1'}}),
            ]),
        ]))
    return out

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'House price: $700k vs $900k vs $1.0M'),
    ('description', (
        'Two 37-year-olds, $400,000 gross (~$292,000 net), no student debt. House bought '
        '2027 with 20% down on a 30-year fixed at 6.5%; property tax 1.6%, insurance 0.4%, '
        'maintenance 1.0% of value annually. Mortgage principal and interest is modeled as '
        'NOMINAL, so it erodes in real terms over the 30 years, while tax, insurance and '
        'maintenance are real and persist for life. All three variants start from the same '
        'total balance sheet (portfolio plus the largest down payment held in cash) so the '
        'cheaper house is not credited twice. Crossed with savings rate and retirement age '
        'to show whether the housing effect depends on them. The metric is median '
        'first-year general (lifestyle) retirement spending, which excludes the earmarked '
        'housing costs themselves. Home equity is NOT counted -- see the companion note.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'house', 'name': 'House price', 'variants': house_variants()},
        {'id': 'savings', 'name': 'Savings rate', 'variants': [
            collections.OrderedDict([
                ('id', vid), ('name', name),
                ('events', [event('save', 'Net investable savings', 'savings',
                                  {'perYear': amt},
                                  {'from': {'named': 'now'},
                                   'to': {'named': 'lastWorkingMonth', 'person': 'person1'}})]),
            ]) for vid, (name, amt) in SAVINGS.items()]},
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

for name, obj in [('base.scenario.json', base), ('grid.json', grid)]:
    with open(os.path.join(HERE, name), 'w') as f:
        json.dump(obj, f, indent=2); f.write('\n')

print(f"{'house':8} {'down':>9} {'P&I/yr':>9} {'carry/yr':>9} {'yr1 total':>10}")
for vid, price in HOUSES.items():
    n = house_numbers(price)
    print(f"${price//1000}k{'':3} {n['down']:>9,.0f} {n['pi']:>9,.0f} "
          f"{n['carry']:>9,.0f} {n['pi']+n['carry']:>10,.0f}")
print(f"\ndescription chars: {len(grid['description'])}")
print(f"combos: {len(HOUSES)*len(SAVINGS)*len(RETIRE)} x 3 conditions = "
      f"{len(HOUSES)*len(SAVINGS)*len(RETIRE)*3} sims")
