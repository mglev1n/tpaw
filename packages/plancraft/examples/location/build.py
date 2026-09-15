#!/usr/bin/env python3
"""Main Line (Lower Merion, PA) vs Cherry Hill (NJ) at ~$500k gross.

Four effects pull in different directions and have to be modeled separately or
the answer is meaningless:

  1. House price      -- the same family home costs far less in Cherry Hill.
  2. Property tax     -- NJ's effective rate is higher, on a cheaper house.
  3. Income tax WHILE WORKING -- both spouses work in Philadelphia, so both pay
     the Philadelphia non-resident wage tax either way. NJ credits that tax
     against NJ income tax; Pennsylvania does NOT credit a local tax against
     the state tax. That asymmetry is the whole game during working years.
  4. Income tax IN RETIREMENT -- Pennsylvania exempts 401(k)/IRA/pension income
     entirely; New Jersey taxes it, with the retirement-income exclusion fully
     phased out at this income level.

Effects 3 and 4 point in OPPOSITE directions, which is why this cannot be
answered with a single "state tax rate".

RATES BLOCK BELOW IS THE ONLY THING THAT NEEDS UPDATING when better figures
land -- everything else derives from it.
"""
import collections, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR, BUY_YEAR = 2026, 2027
CURRENT_AGE, MAX_AGE = 37, 95
GROSS = 500_000
PORTFOLIO_NOW = 400_000
MORTGAGE_RATE, MORTGAGE_YEARS, DOWN_PCT = 0.065, 30, 0.20

# ---------------------------------------------------------------------------
# RATES  (provisional; replace with researched figures)
# ---------------------------------------------------------------------------
PHILLY_NONRESIDENT_WAGE = 0.0344   # paid from either state when working in Philly
PA_STATE = 0.0307
LOWER_MERION_EIT = 0.0             # credited away by the Philadelphia wage tax
NJ_MFJ_BRACKETS = [(20_000,.014),(50_000,.0175),(70_000,.0245),(80_000,.035),
                   (150_000,.05525),(500_000,.0637),(1_000_000,.0897),(10**9,.1075)]
PROPERTY_TAX = {'pa': 0.019, 'nj': 0.026}     # effective, on MARKET value
INSURANCE_PCT, MAINTENANCE_PCT = 0.004, 0.010
# Share of retirement withdrawals coming from tax-deferred accounts; the rest
# is Roth or already-taxed basis. NJ taxes only the tax-deferred share, and
# taxes no Social Security at all.
TAX_DEFERRED_SHARE = 0.70

def nj_tax(taxable):
    t, prev = 0.0, 0
    for cap, rate in NJ_MFJ_BRACKETS:
        if taxable > prev:
            t += (min(taxable, cap) - prev) * rate
        prev = cap
    return t

def federal_and_payroll(gross, e1, e2):
    std = 31_500
    taxable = max(0, gross - std)
    brk = [(24_000,.10),(97_000,.12),(207_000,.22),(395_000,.24),(502_000,.32),
           (752_000,.35),(10**9,.37)]
    fed, prev = 0.0, 0
    for cap, rate in brk:
        if taxable > prev: fed += (min(taxable, cap) - prev) * rate
        prev = cap
    WB = 184_000
    payroll = (min(e1,WB)+min(e2,WB))*.062 + gross*.0145 + max(0,gross-250_000)*.009
    return fed, payroll

def working_net(state):
    """Net income while both spouses work in Philadelphia."""
    e1, e2 = GROSS*0.55, GROSS*0.45
    fed, payroll = federal_and_payroll(GROSS, e1, e2)
    philly = GROSS * PHILLY_NONRESIDENT_WAGE
    if state == 'pa':
        # PA taxes residents at the flat rate; the Philadelphia wage tax credits
        # against the LOCAL earned income tax, not against the state tax.
        state_local = GROSS*PA_STATE + max(0, GROSS*LOWER_MERION_EIT - philly)
    else:
        # NJ credits tax paid to another jurisdiction, capped at the NJ tax on
        # that same income -- here all of it is Philadelphia-sourced.
        gross_nj = nj_tax(GROSS)
        state_local = max(0, gross_nj - philly)
    return GROSS - fed - payroll - philly - state_local, dict(
        fed=fed, payroll=payroll, philly=philly, state_local=state_local)

def nj_retirement_tax(withdrawals):
    """NJ tax on retirement withdrawals. Social Security is not taxed by NJ and
    the retirement-income exclusion is fully phased out above $150k."""
    return nj_tax(withdrawals * TAX_DEFERRED_SHARE)

def pmt(P):
    r = MORTGAGE_RATE/12; n = MORTGAGE_YEARS*12
    return P*r/(1-(1+r)**-n)*12

# ---------------------------------------------------------------------------
# Location and house variants. Price and state move together, so they are one
# dimension -- a Cherry Hill house at a Main Line price is a different house.
# ---------------------------------------------------------------------------
LOCATIONS = collections.OrderedDict([
    ('ml-900',   ('Main Line, $900k',        'pa',  900_000)),
    ('ml-1200',  ('Main Line, $1.2M',        'pa', 1_200_000)),
    ('ch-550',   ('Cherry Hill, $550k (=ML $900k house)', 'nj', 550_000)),
    ('ch-750',   ('Cherry Hill, $750k',      'nj',  750_000)),
    ('ch-900',   ('Cherry Hill, $900k (same spend)', 'nj', 900_000)),
])
SAVINGS_RATES = collections.OrderedDict([('hi', 0.40), ('mid', 0.31), ('lo', 0.23)])
RETIRE = [55, 60, 65]
SS = {55: (3600, 3200), 60: (4000, 3500), 65: (4400, 3800)}
# First-pass estimate of annual retirement withdrawals, refined after a run.
ASSUMED_WITHDRAWAL = 190_000

def event(i, label, kind, amount, timing, nominal=False):
    e = collections.OrderedDict([('id',i),('label',label),('kind',kind),('amount',amount)])
    if nominal: e['nominal'] = True
    e['timing'] = timing
    return e

MAX_DOWN = max(p for _,_,p in LOCATIONS.values()) * DOWN_PCT

base = collections.OrderedDict([
    ('plancraft', 1),
    ('meta', {'name': 'Main Line vs Cherry Hill at $500k gross',
              'description': ('Two 37-year-olds, $500,000 gross, both working in '
                              'Philadelphia, no student debt. $400,000 invested plus '
                              'down-payment cash. Real 2026 dollars, net of tax.'),
              'anchorYear': ANCHOR}),
    ('household', {'person1': {'currentAge':{'years':CURRENT_AGE},'retirementAge':{'years':65},
                               'maxAge':{'years':MAX_AGE}},
                   'person2': {'currentAge':{'years':CURRENT_AGE},'retirementAge':{'years':65},
                               'maxAge':{'years':MAX_AGE}},
                   'withdrawalStart': 'person1'}),
    ('portfolio', {'balance': PORTFOLIO_NOW + MAX_DOWN}),
    ('events', []),
    ('simulation', {'expectedReturns': {'fixed': {'stocks':0.05,'bonds':0.02}},
                    'inflation': {'manual': 0.024},
                    'sampling': {'type':'monteCarlo','numRuns':2000,'seed':1776},
                    'legacy': 0}),
])

PA_NET_EARLY, _ = working_net('pa')
NJ_NET_EARLY, _ = working_net('nj')


def location_variants():
    out = []
    for vid, (name, state, price) in LOCATIONS.items():
        down = price*DOWN_PCT
        carry = price*(PROPERTY_TAX[state] + INSURANCE_PCT + MAINTENANCE_PCT)
        evs = [
            event('house-down','Down payment (20%)','expenseEssential',
                  {'oneTime': round(down)}, {'at':{'calendarYear':BUY_YEAR,'month':6}}),
            event('house-pi','Mortgage principal and interest','expenseEssential',
                  {'perYear': round(pmt(price-down))},
                  {'from':{'calendarYear':BUY_YEAR,'month':1},
                   'to':{'calendarYear':BUY_YEAR+MORTGAGE_YEARS-1,'month':12}}, nominal=True),
            event('house-carry','Property tax, insurance, maintenance','expenseEssential',
                  {'perYear': round(carry)},
                  {'from':{'calendarYear':BUY_YEAR,'month':1},
                   'to':{'named':'maxAge','person':'person1'}}),
        ]
        if state == 'nj':
            # Consumption is held equal across locations, so NJ's higher net
            # income during the working years is banked rather than spent.
            evs.append(event('save-state-diff','Extra savings from NJ net income',
                             'savings', {'perYear': round(NJ_NET_EARLY - PA_NET_EARLY)},
                             {'from':{'named':'now'},
                              'to':{'named':'lastWorkingMonth','person':'person1'}}))
            # PA exempts retirement income entirely, so this line exists only
            # for the New Jersey variants.
            evs.append(event('nj-ret-tax','NJ income tax on retirement withdrawals',
                             'expenseEssential',
                             {'perYear': round(nj_retirement_tax(ASSUMED_WITHDRAWAL))},
                             {'from':{'named':'retirement','person':'person1'},
                              'to':{'named':'maxAge','person':'person1'}}))
        out.append(collections.OrderedDict([('id',vid),('name',name),('events',evs)]))
    return out

# Savings depends on the state (different net income), and the state is set by
# the location dimension -- so savings is expressed as a RATE and the dollar
# amount is folded into the location variants would double the dimension. Keep
# them separate by using the PA net as the reference and charging NJ the
# difference as an explicit expense, which keeps both dimensions independent.
PA_NET, PA_PARTS = working_net('pa')
NJ_NET, NJ_PARTS = working_net('nj')

def savings_dimension():
    return [collections.OrderedDict([
        ('id', rid), ('name', f'Save {int(rate*100)}% of net (${int(round(PA_NET*rate,-3)):,})'),
        ('events', [event('save','Net investable savings','savings',
                          {'perYear': int(round(PA_NET*rate,-3))},
                          {'from':{'named':'now'},
                           'to':{'named':'lastWorkingMonth','person':'person1'}})]),
    ]) for rid, rate in SAVINGS_RATES.items()]

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Main Line vs Cherry Hill at $500k gross'),
    ('description', (
        'Two 37-year-olds, $500,000 gross, BOTH WORKING IN PHILADELPHIA, no student debt, '
        '$400,000 invested plus down-payment cash, house bought 2027 with 20% down on a '
        '30-year fixed at 6.5%. Location and house price are one dimension because a Cherry '
        'Hill house at a Main Line price is a different house; the $550k Cherry Hill variant '
        'is meant to be the same house as the $900k Main Line one. Four effects are modeled '
        'separately: house price, property tax (effective rate on market value, higher in NJ '
        'on a cheaper house), income tax while working, and income tax in retirement. The '
        'working-years comparison turns on an asymmetry -- both spouses pay the Philadelphia '
        'non-resident wage tax either way, New Jersey credits that tax against NJ income tax, '
        'and Pennsylvania does not credit a local tax against the state tax. The retirement '
        'comparison runs the other way, since Pennsylvania exempts 401(k), IRA and pension '
        'income entirely while New Jersey taxes it with the retirement-income exclusion fully '
        'phased out at this income. Consumption is held equal across locations, so the higher '
        'NJ net income during working years is banked. Mortgage principal and interest is '
        'nominal and erodes in real terms; carrying costs are real and continue for life.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'location', 'name': 'Location and house', 'variants': location_variants()},
        {'id': 'savings', 'name': 'Savings rate', 'variants': savings_dimension()},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', [
                    event('ss-1','Social Security (person 1, at 70)','retirementIncome',
                          {'perMonth': SS[a][0]},
                          {'from':{'age':{'person':'person1','years':70}},
                           'to':{'named':'maxAge','person':'person1'}}),
                    event('ss-2','Social Security (person 2, at 70)','retirementIncome',
                          {'perMonth': SS[a][1]},
                          {'from':{'age':{'person':'person2','years':70}},
                           'to':{'named':'maxAge','person':'person2'}}),
                ]),
            ]) for a in RETIRE]},
    ]),
    ('conditions', [
        {'id':'pessimistic','name':'Pessimistic (3.5%/1.5%)',
         'simulation':{'expectedReturns':{'fixed':{'stocks':0.035,'bonds':0.015}}}},
        {'id':'base-returns','name':'Base (5%/2%)',
         'simulation':{'expectedReturns':{'fixed':{'stocks':0.05,'bonds':0.02}}}},
        {'id':'optimistic','name':'Optimistic (6.5%/3%)',
         'simulation':{'expectedReturns':{'fixed':{'stocks':0.065,'bonds':0.03}}}},
    ]),
])

for _name, _obj in [('base.scenario.json', base), ('grid.json', grid)]:
    with open(os.path.join(HERE, _name), 'w') as _f:
        json.dump(_obj, _f, indent=2); _f.write('\n')

if __name__ == '__main__':
    print(f"Gross ${GROSS:,}, both working in Philadelphia\n")
    for st, label in (('pa','Lower Merion PA'), ('nj','Cherry Hill NJ')):
        net, p = working_net(st)
        print(f"  {label:18} fed ${p['fed']:>9,.0f} | payroll ${p['payroll']:>8,.0f} "
              f"| Philly ${p['philly']:>8,.0f} | state/local ${p['state_local']:>8,.0f} "
              f"| NET ${net:>9,.0f}")
    print(f"  working-years difference: ${NJ_NET-PA_NET:>+,.0f}/yr "
          f"({'NJ cheaper' if NJ_NET>PA_NET else 'PA cheaper'})\n")
    print(f"  NJ retirement tax on ${ASSUMED_WITHDRAWAL:,} of withdrawals "
          f"({int(TAX_DEFERRED_SHARE*100)}% tax-deferred): "
          f"${nj_retirement_tax(ASSUMED_WITHDRAWAL):,.0f}/yr   PA: $0\n")
    print(f"{'location':40} {'price':>10} {'P&I':>9} {'carry':>9} {'yr1':>10}")
    for vid,(name,state,price) in LOCATIONS.items():
        down=price*DOWN_PCT
        carry=price*(PROPERTY_TAX[state]+INSURANCE_PCT+MAINTENANCE_PCT)
        print(f"{name:40} {price:>10,} {pmt(price-down):>9,.0f} {carry:>9,.0f} "
              f"{pmt(price-down)+carry:>10,.0f}")
