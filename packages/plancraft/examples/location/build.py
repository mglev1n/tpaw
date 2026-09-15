#!/usr/bin/env python3
"""Main Line (Lower Merion, PA) vs Cherry Hill (NJ) at ~$500k gross.

Four effects, two of which point in OPPOSITE directions -- which is why this
cannot be answered with a single "state tax rate":

  1. House price. A comparable 4-bedroom home costs ~1.8x more on the Main
     Line (Zillow ZHVI 4BR, Jul 2026: Bryn Mawr $1,179,945 / Wynnewood
     $1,068,301 / Cherry Hill 08003 $654,591).
  2. Property tax. Lower Merion's effective rate on MARKET value is only
     ~1.407% -- Montgomery County has not reassessed since 1998 and the common
     level ratio is 29.76% against 47.2727 mills. Cherry Hill is ~2.699%
     (all-in $4.969/$100 at a 54.32% equalization ratio, including the separate
     fire district levy). So NJ's rate is ~1.9x PA's, on a much cheaper house:
     at the SAME HOUSE the annual bills nearly cancel, and the difference shows
     up as ~$500k more capital tied up in the Main Line house instead.
  3. Income tax WHILE WORKING. Both spouses pay the Philadelphia non-resident
     wage tax (3.425%) either way. New Jersey credits it in full against NJ
     income tax; Pennsylvania does not credit a local tax against the state
     tax, and Lower Merion levies no EIT of its own to credit it against. So
     PA stacks 3.07% on top with no offset and NJ absorbs it -- NJ is CHEAPER
     by ~$5,750/yr.
  4. Income tax IN RETIREMENT. Pennsylvania exempts 401(k)/IRA/pension income
     entirely. New Jersey taxes it -- but excludes Social Security from NJ
     gross income, and the retirement-income exclusion is worth up to $100,000
     below a hard $150,000 cliff. So the NJ penalty depends on the PORTFOLIO
     DRAW (spending less Social Security), not on total spending, and is
     front-loaded in the years before Social Security begins.

Because of (4) the NJ retirement tax is endogenous -- it depends on the draw the
simulation produces -- and the draw is set jointly by the savings rate, the
retirement age and the house, which are three separate grid dimensions. A
constant cannot express that, and the exclusion is a step function with a hard
cliff, so it cannot be averaged either. The grid therefore runs with the
retirement tax at zero and nj_retirement_tax.py applies it afterwards from the
measured draws; analyze.py folds that into the paired comparison. The
NJ_RET_TAX_* constants below stay as a manual override and are normally zero.
"""
import collections, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR, BUY_YEAR = 2026, 2027
CURRENT_AGE, MAX_AGE = 37, 95
GROSS = 500_000
PORTFOLIO_NOW = 400_000
MORTGAGE_RATE, MORTGAGE_YEARS, DOWN_PCT = 0.065, 30, 0.20

# --- Verified rates (see module docstring for sources) ----------------------
PHILLY_NONRESIDENT = 0.03425
PA_STATE, LOWER_MERION_EIT = 0.0307, 0.0
PROPERTY_TAX = {'pa': 0.01407, 'nj': 0.02699}
INSURANCE_PCT, MAINTENANCE_PCT = 0.004, 0.010
NJ_BRACKETS = [(20_000,.014),(50_000,.0175),(70_000,.0245),(80_000,.035),
               (150_000,.05525),(500_000,.0637),(1_000_000,.0897),(10**9,.1075)]
NJ_PROP_TAX_DEDUCTION_CAP = 15_000
# NJ costs more on these regardless of phase.
NJ_AUTO_INSURANCE_EXTRA = 2_250     # two vehicles, full coverage
NJ_SALES_TAX_EXTRA = 375            # 0.625 pts on ~$60k taxable consumption

# Set from pass 1. Net of Stay NJ + ANCHOR property tax relief, which is
# income-tiered and politically fragile -- see NJ_RELIEF note below.
NJ_RET_TAX_PRE_SS = 0
NJ_RET_TAX_POST_SS = 0

def nj_tax(taxable):
    out, prev = 0.0, 0
    for cap, rate in NJ_BRACKETS:
        if taxable > prev: out += (min(taxable, cap) - prev) * rate
        prev = cap
    return out

def nj_retirement_tax(draw, age65plus=True, include_relief=True):
    """NJ tax on an annual portfolio draw, net of property tax relief.

    Social Security is excluded from NJ gross income, so the draw -- not total
    spending -- is what NJ sees. The exclusion is a step function with a hard
    cliff at $150,000, not a smooth phase-out."""
    if draw <= 100_000:   excl = min(draw, 100_000)
    elif draw <= 125_000: excl = draw * 0.50
    elif draw <= 150_000: excl = draw * 0.25
    else:                 excl = 0.0
    exemptions = 4_000 if age65plus else 2_000
    tax = nj_tax(max(0, draw - excl - exemptions - NJ_PROP_TAX_DEDUCTION_CAP))
    if not include_relief:
        return tax
    stay = 6_500 if draw <= 100_000 else 5_000 if draw <= 150_000 else 4_000 if draw <= 200_000 else 0
    anchor = 1_750 if draw <= 150_000 else 1_250 if draw <= 250_000 else 0
    return tax - stay - anchor

def federal_and_payroll(gross):
    taxable = max(0, gross - 31_500)
    brk = [(24_000,.10),(97_000,.12),(207_000,.22),(395_000,.24),(502_000,.32),
           (752_000,.35),(10**9,.37)]
    fed, prev = 0.0, 0
    for cap, rate in brk:
        if taxable > prev: fed += (min(taxable, cap) - prev) * rate
        prev = cap
    e1, e2, WB = gross*0.55, gross*0.45, 184_000
    payroll = (min(e1,WB)+min(e2,WB))*.062 + gross*.0145 + max(0,gross-250_000)*.009
    return fed, payroll

def working_net(state):
    fed, payroll = federal_and_payroll(GROSS)
    philly = GROSS * PHILLY_NONRESIDENT
    if state == 'pa':
        state_local = GROSS*PA_STATE + max(0, GROSS*LOWER_MERION_EIT - philly)
    else:
        before = nj_tax(GROSS - 2_000 - NJ_PROP_TAX_DEDUCTION_CAP)
        state_local = max(0, before - philly)   # Philadelphia credit is full here
    return GROSS - fed - payroll - philly - state_local

PA_NET, NJ_NET = working_net('pa'), working_net('nj')

def pmt(P):
    r = MORTGAGE_RATE/12; n = MORTGAGE_YEARS*12
    return P*r/(1-(1+r)**-n)*12

# Zillow ZHVI 4-bedroom, July 2026. Price and state move together: a Cherry
# Hill house at a Main Line price is a different house.
LOCATIONS = collections.OrderedDict([
    ('ml-brynmawr',  ('Bryn Mawr $1.18M',            'pa', 1_179_945)),
    ('ml-wynnewood', ('Wynnewood $1.07M',            'pa', 1_068_301)),
    ('ch-08003',     ('Cherry Hill $655k (= Bryn Mawr house)', 'nj', 654_591)),
    ('ch-08034',     ('Cherry Hill $572k',           'nj',   572_405)),
    ('ch-samespend', ('Cherry Hill $1.07M (same spend)',      'nj', 1_068_301)),
])
SAVINGS_RATES = collections.OrderedDict([('hi',0.40),('mid',0.31),('lo',0.23)])
RETIRE = [55, 60, 65]
SS = {55: (3600, 3200), 60: (4000, 3500), 65: (4400, 3800)}

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
    ('household', {'person1':{'currentAge':{'years':CURRENT_AGE},'retirementAge':{'years':65},
                              'maxAge':{'years':MAX_AGE}},
                   'person2':{'currentAge':{'years':CURRENT_AGE},'retirementAge':{'years':65},
                              'maxAge':{'years':MAX_AGE}},
                   'withdrawalStart':'person1'}),
    ('portfolio', {'balance': PORTFOLIO_NOW + MAX_DOWN}),
    ('events', []),
    ('simulation', {'expectedReturns':{'fixed':{'stocks':0.05,'bonds':0.02}},
                    'inflation':{'manual':0.024},
                    'sampling':{'type':'monteCarlo','numRuns':2000,'seed':1776},
                    'legacy':0}),
])

def location_variants():
    out = []
    for vid,(name,state,price) in LOCATIONS.items():
        down = price*DOWN_PCT
        carry = price*(PROPERTY_TAX[state] + INSURANCE_PCT + MAINTENANCE_PCT)
        evs = [
            event('house-down','Down payment (20%)','expenseEssential',
                  {'oneTime':round(down)}, {'at':{'calendarYear':BUY_YEAR,'month':6}}),
            event('house-pi','Mortgage principal and interest','expenseEssential',
                  {'perYear':round(pmt(price-down))},
                  {'from':{'calendarYear':BUY_YEAR,'month':1},
                   'to':{'calendarYear':BUY_YEAR+MORTGAGE_YEARS-1,'month':12}}, nominal=True),
            event('house-carry','Property tax, insurance, maintenance','expenseEssential',
                  {'perYear':round(carry)},
                  {'from':{'calendarYear':BUY_YEAR,'month':1},
                   'to':{'named':'maxAge','person':'person1'}}),
        ]
        if state == 'nj':
            # Consumption is held equal across locations, so NJ's lower income
            # tax while working is banked rather than spent.
            evs.append(event('save-nj-tax-edge','Banked NJ income tax advantage','savings',
                             {'perYear':round(NJ_NET-PA_NET)},
                             {'from':{'named':'now'},
                              'to':{'named':'lastWorkingMonth','person':'person1'}}))
            evs.append(event('nj-other','NJ auto insurance and sales tax premium',
                             'expenseEssential',
                             {'perYear':NJ_AUTO_INSURANCE_EXTRA+NJ_SALES_TAX_EXTRA},
                             {'from':{'named':'now'},
                              'to':{'named':'maxAge','person':'person1'}}))
            if NJ_RET_TAX_PRE_SS:
                evs.append(event('nj-ret-tax-pre','NJ tax on withdrawals, before Social Security',
                                 'expenseEssential', {'perYear':NJ_RET_TAX_PRE_SS},
                                 {'from':{'named':'retirement','person':'person1'},
                                  'to':{'age':{'person':'person1','years':70}}}))
            if NJ_RET_TAX_POST_SS:
                evs.append(event('nj-ret-tax-post','NJ tax on withdrawals, with Social Security',
                                 'expenseEssential', {'perYear':NJ_RET_TAX_POST_SS},
                                 {'from':{'age':{'person':'person1','years':70}},
                                  'to':{'named':'maxAge','person':'person1'}}))
        out.append(collections.OrderedDict([('id',vid),('name',name),('events',evs)]))
    return out

def savings_dimension():
    return [collections.OrderedDict([
        ('id',rid), ('name',f'Save {int(rate*100)}% of net (${int(round(PA_NET*rate,-3)):,})'),
        ('events',[event('save','Net investable savings','savings',
                         {'perYear':int(round(PA_NET*rate,-3))},
                         {'from':{'named':'now'},
                          'to':{'named':'lastWorkingMonth','person':'person1'}})]),
    ]) for rid, rate in SAVINGS_RATES.items()]

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Main Line vs Cherry Hill at $500k gross'),
    ('description', (
        'Two 37-year-olds, $500,000 gross, BOTH WORKING IN PHILADELPHIA, no student debt, '
        '$400,000 invested plus down-payment cash, house bought 2027 with 20% down at 6.5%. '
        'House prices are Zillow ZHVI 4-bedroom, July 2026, so the $655k Cherry Hill variant '
        'is the same house as the $1.18M Bryn Mawr one; a Cherry Hill house at a Main Line '
        'price is a different house, which is why location and price are one dimension. '
        'Effective property tax on market value is 1.407% in Lower Merion (Montgomery County '
        'has not reassessed since 1998; 47.2727 mills at a 29.76% common level ratio) against '
        '2.699% in Cherry Hill (all-in $4.969/$100 at a 54.32% equalization ratio, including '
        'the fire district levy). While working, both spouses pay the 3.425% Philadelphia '
        'non-resident wage tax either way; New Jersey credits it in full against NJ income '
        'tax while Pennsylvania cannot credit a local tax against the state tax and Lower '
        'Merion levies no EIT, so NJ is about $5,750/yr cheaper and that difference is banked. '
        'In retirement the sign flips: Pennsylvania exempts retirement income entirely, while '
        'New Jersey taxes the portfolio draw -- Social Security is excluded from NJ gross '
        'income and the retirement-income exclusion reaches $100,000 below a hard $150,000 '
        'cliff, so the NJ penalty is front-loaded before Social Security begins. NJ auto '
        'insurance and sales tax premiums are carried for life.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id':'location','name':'Location and house','variants':location_variants()},
        {'id':'savings','name':'Savings rate','variants':savings_dimension()},
        {'id':'retire','name':'Retirement age','variants':[
            collections.OrderedDict([
                ('id',f'r{a}'), ('name',f'Retire at {a}'),
                ('household',{'person1':{'retirementAge':{'years':a}},
                              'person2':{'retirementAge':{'years':a}}}),
                ('events',[
                    event('ss-1','Social Security (person 1, at 70)','retirementIncome',
                          {'perMonth':SS[a][0]},
                          {'from':{'age':{'person':'person1','years':70}},
                           'to':{'named':'maxAge','person':'person1'}}),
                    event('ss-2','Social Security (person 2, at 70)','retirementIncome',
                          {'perMonth':SS[a][1]},
                          {'from':{'age':{'person':'person2','years':70}},
                           'to':{'named':'maxAge','person':'person2'}}),
                ]),
            ]) for a in RETIRE]},
    ]),
    ('conditions',[
        {'id':'pessimistic','name':'Pessimistic (3.5%/1.5%)',
         'simulation':{'expectedReturns':{'fixed':{'stocks':0.035,'bonds':0.015}}}},
        {'id':'base-returns','name':'Base (5%/2%)',
         'simulation':{'expectedReturns':{'fixed':{'stocks':0.05,'bonds':0.02}}}},
        {'id':'optimistic','name':'Optimistic (6.5%/3%)',
         'simulation':{'expectedReturns':{'fixed':{'stocks':0.065,'bonds':0.03}}}},
    ]),
])

for _n,_o in [('base.scenario.json',base),('grid.json',grid)]:
    with open(os.path.join(HERE,_n),'w') as f:
        json.dump(_o,f,indent=2); f.write('\n')

if __name__ == '__main__':
    print(f"working net: PA ${PA_NET:,.0f}  NJ ${NJ_NET:,.0f}  -> NJ banks ${NJ_NET-PA_NET:,.0f}/yr")
    print(f"NJ retirement tax (net of Stay NJ + ANCHOR) at sample draws:")
    for d in (80_000,100_000,140_000,160_000,200_000):
        print(f"   draw ${d:>7,} -> ${nj_retirement_tax(d):>+8,.0f}")
    print(f"\n{'location':42}{'price':>11}{'P&I':>10}{'carry':>10}{'yr1':>11}")
    for vid,(name,state,price) in LOCATIONS.items():
        carry = price*(PROPERTY_TAX[state]+INSURANCE_PCT+MAINTENANCE_PCT)
        print(f"{name:42}{price:>11,}{pmt(price*(1-DOWN_PCT)):>10,.0f}{carry:>10,.0f}"
              f"{pmt(price*(1-DOWN_PCT))+carry:>11,.0f}")
    print(f"\ndescription chars: {len(grid['description'])}")
