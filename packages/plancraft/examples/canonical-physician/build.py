#!/usr/bin/env python3
"""Generate canonical high-income physician households and their decision grids.

Two deliberately different households, so the effect-size ranking can be
tested for stability across household type rather than asserted from one case:

  A  Dual income, moderate debt. Two 35-year-olds, ~$410k gross / $270k net,
     $150k invested, $215k of student loans.
  B  Single earner, heavy debt. A 38-year-old surgeon out of a long training
     path, ~$600k gross / $370k net, $50k invested, $400k of student loans,
     non-earning spouse (so Social Security is a spousal benefit).

Both are synthetic and representative rather than anyone's actual finances.
Every figure is real 2026 dollars and NET of tax -- the engine models one
portfolio and takes net contributions, so tax is handled upstream.

The five dimensions are structurally identical across households and the
savings variants use the same PERCENTAGES of net income, so the comparison
asks whether the same relative choice carries the same relative weight.

Run: python3 build.py   (writes base/grid/fees/params for each household)
"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = 2026
KID_BIRTH = [2027, 2029, 2031]
FIVE_TWO_NINE_PER_MONTH = 500
COLLEGE_TOPUP_PER_YEAR = 25_000

# Savings variants as a share of net income, identical across households.
SAVINGS_SHARES = collections.OrderedDict([
    ('hyper', ('Hyper-saver (41% of net)', 0.41, 0.0)),
    ('high', ('High (31%)', 0.31, 0.0)),
    ('moderate', ('Moderate (23%)', 0.23, 0.0)),
    ('creep', ('Creeping (31% falling 2%/yr)', 0.31, -2.0)),
])

HOUSEHOLDS = {
    'a': dict(
        key='a',
        label='Household A - dual income, moderate debt',
        blurb=('Two 35-year-olds two years out of training. Household gross ~$410k '
               '(physician ~$325k + spouse ~$85k), ~$270,000 net. $150,000 invested. '
               'Real income held flat.'),
        current_age=35,
        net_income=270_000,
        portfolio=150_000,
        # (label, annual payment, years) for ~$215k at 6.5%
        loans=collections.OrderedDict([
            ('aggressive', ('Aggressive (5 yr)', 48_000, 5)),
            ('standard', ('Standard (10 yr)', 29_000, 10)),
            ('idr', ('Income-driven (20 yr)', 19_000, 20)),
        ]),
        housing=collections.OrderedDict([
            ('modest', ('Modest (~$550k)', 0)),
            ('typical', ('Typical (~$850k)', 14_000)),
            ('doctor', ('Doctor house (~$1.3M)', 30_000)),
        ]),
        private_k12=30_000,
        # retirement age -> (person1 $/mo, person2 $/mo), both claimed at 70
        ss={55: (3400, 2100), 60: (3800, 2350), 65: (4200, 2600), 70: (4400, 2700)},
        ss_note=('Both spouses earn, so each claims their own benefit at 70, scaled '
                 'down at earlier retirement ages for the shorter earnings record.'),
    ),
    'b': dict(
        key='b',
        label='Household B - single earner, heavy debt',
        blurb=('A 38-year-old surgeon out of a long training path, sole earner. Gross '
               '~$600k, ~$370,000 net. $50,000 invested -- a late start with a large '
               'balance outstanding. Real income held flat.'),
        current_age=38,
        net_income=370_000,
        portfolio=50_000,
        # ~$400k at 6.8%, amortized over each term
        loans=collections.OrderedDict([
            ('aggressive', ('Aggressive (5 yr)', 97_000, 5)),
            ('standard', ('Standard (10 yr)', 56_000, 10)),
            ('idr', ('Income-driven (20 yr)', 37_000, 20)),
        ]),
        housing=collections.OrderedDict([
            ('modest', ('Modest (~$700k)', 0)),
            ('typical', ('Typical (~$1.1M)', 20_000)),
            ('doctor', ('Doctor house (~$1.8M)', 44_000)),
        ]),
        private_k12=30_000,
        # Sole earner maxes the taxable wage base; the spouse takes a spousal
        # benefit, which earns no delayed-retirement credit past FRA.
        ss={55: (3600, 1500), 60: (4000, 1650), 65: (4400, 1800), 70: (4600, 1850)},
        ss_note=('Only one spouse earns, so the second benefit is spousal (roughly half '
                 'the earner PIA) and takes no delayed-retirement credit.'),
    ),
}

EDUCATION = collections.OrderedDict([
    ('two-public', ('2 kids, public school', 2, False)),
    ('two-private', ('2 kids, private K-12 + college', 2, True)),
    ('three-public', ('3 kids, public school', 3, False)),
])

CONDITIONS = [
    {'id': 'pessimistic', 'name': 'Pessimistic (3.5%/1.5%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.035, 'bonds': 0.015}}}},
    {'id': 'base-returns', 'name': 'Base (5%/2%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}}}},
    {'id': 'optimistic', 'name': 'Optimistic (6.5%/3%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.065, 'bonds': 0.03}}}},
]

FEES = collections.OrderedDict([
    ('diy', ('DIY index (0.05%)', 0.0495, 0.0195)),
    ('lowcost', ('Low-cost advisor (0.40%)', 0.046, 0.016)),
    ('typical', ('Typical AUM (0.75%)', 0.0425, 0.0125)),
    ('full', ('Full-service AUM (1.10%)', 0.039, 0.009)),
])


def event(id_, label, kind, amount, timing, growth=None):
    e = collections.OrderedDict(
        [('id', id_), ('label', label), ('kind', kind), ('amount', amount)])
    if growth:
        e['growth'] = {'annualPercent': growth}
    e['timing'] = timing
    return e


def span(a, b, from_month=1, to_month=12):
    return {'from': {'calendarYear': a, 'month': from_month},
            'to': {'calendarYear': b, 'month': to_month}}


def savings_variants(h):
    out = []
    for vid, (name, share, growth) in SAVINGS_SHARES.items():
        amount = int(round(h['net_income'] * share, -3))
        out.append(collections.OrderedDict([
            ('id', vid), ('name', name),
            ('events', [event('save', 'Net investable savings', 'savings',
                              {'perYear': amount},
                              {'from': {'named': 'now'},
                               'to': {'named': 'lastWorkingMonth', 'person': 'person1'}},
                              growth=growth or None)]),
        ]))
    return out


def retirement_variants(h):
    return [collections.OrderedDict([
        ('id', f'r{age}'), ('name', f'Retire at {age}'),
        ('household', {'person1': {'retirementAge': {'years': age}},
                       'person2': {'retirementAge': {'years': age}}}),
        ('events', [
            event('ss-1', 'Social Security (earner, at 70)', 'retirementIncome',
                  {'perMonth': p1},
                  {'from': {'age': {'person': 'person1', 'years': 70}},
                   'to': {'named': 'maxAge', 'person': 'person1'}}),
            event('ss-2', 'Social Security (spouse)', 'retirementIncome',
                  {'perMonth': p2},
                  {'from': {'age': {'person': 'person2', 'years': 70}},
                   'to': {'named': 'maxAge', 'person': 'person2'}}),
        ]),
    ]) for age, (p1, p2) in h['ss'].items()]


def loan_variants(h):
    return [collections.OrderedDict([
        ('id', vid), ('name', name),
        ('events', [event('loans', 'Student loan payments', 'expenseEssential',
                          {'perYear': per_year}, span(ANCHOR, ANCHOR + years - 1))]),
    ]) for vid, (name, per_year, years) in h['loans'].items()]


def housing_variants(h):
    out = []
    for vid, (name, inc) in h['housing'].items():
        events = [event('housing', 'Housing cost above baseline', 'expenseEssential',
                        {'perYear': inc}, span(2027, 2056))] if inc else []
        out.append(collections.OrderedDict(
            [('id', vid), ('name', name), ('events', events)]))
    return out


def education_variants(h):
    out = []
    for vid, (name, n_kids, private) in EDUCATION.items():
        events = []
        for i in range(n_kids):
            b = KID_BIRTH[i]
            events.append(event(f'c529-{i+1}', f'529 (child {i+1})', 'expenseEssential',
                                {'perMonth': FIVE_TWO_NINE_PER_MONTH}, span(b, b + 18)))
            if private:
                events.append(event(f'k12-{i+1}', f'Private K-12 (child {i+1})',
                                    'expenseEssential', {'perYear': h['private_k12']},
                                    span(b + 5, b + 18, 9, 6)))
                events.append(event(f'college-{i+1}', f'College top-up (child {i+1})',
                                    'expenseEssential',
                                    {'perYear': COLLEGE_TOPUP_PER_YEAR},
                                    span(b + 18, b + 22, 9, 6)))
        out.append(collections.OrderedDict(
            [('id', vid), ('name', name), ('events', events)]))
    return out



# --- Retiree healthcare, for the consumption-ratio sensitivity ---------------
# Fidelity's 2026 Retiree Health Care Cost Estimate is $185,500 per 65-year-old
# individual (~$371,000 per couple) over retirement, covering Medicare premiums,
# cost sharing and uncovered drugs, and explicitly EXCLUDING long-term care.
# Modeled as $8,000/yr at 65 growing 2.5%/yr real, which averages ~$11,900/yr
# over a 30-year retirement and back-loads it the way medical spending actually
# arrives. The long-term-care line is an expected-value approximation and is far
# rougher than the Fidelity figure -- flagged as such rather than dressed up.
HEALTH = collections.OrderedDict([
    ('none', ('No healthcare line (as in the main grid)', 0, 0)),
    ('medicare', ('Medicare premiums + cost sharing', 8_000, 0)),
    ('medicare-ltc', ('Medicare + long-term care allowance', 8_000, 25_000)),
])


def health_variants(h):
    out = []
    for vid, (name, med, ltc) in HEALTH.items():
        events = []
        if med:
            events.append(event('health', 'Medicare premiums and cost sharing',
                                'expenseEssential', {'perYear': med},
                                {'from': {'named': 'retirement', 'person': 'person1'},
                                 'to': {'named': 'maxAge', 'person': 'person1'}},
                                growth=2.5))
        if ltc:
            events.append(event('ltc', 'Long-term care allowance (expected value)',
                                'expenseEssential', {'perYear': ltc},
                                {'from': {'age': {'person': 'person1', 'years': 85}},
                                 'to': {'named': 'maxAge', 'person': 'person1'}}))
        out.append(collections.OrderedDict(
            [('id', vid), ('name', name), ('events', events)]))
    return out


def build_health_grid(h):
    k = h['key']
    fixed_events = (retirement_variants(h)[2]['events']      # retire-65 Social Security
                    + loan_variants(h)[1]['events']          # standard loans
                    + housing_variants(h)[1]['events']       # typical house
                    + education_variants(h)[0]['events'])    # 2 kids, public
    g = collections.OrderedDict([
        ('plancraftGrid', 1),
        ('name', f'Household {h["key"].upper()}: healthcare and the consumption gap'),
        ('description', (
            f'{h["blurb"]} Isolates how much of the retirement-versus-working consumption '
            f'gap is explained by healthcare costs the main grid omits. Savings rate is '
            f'crossed with three healthcare assumptions; every other decision is held at '
            f'retire 65, standard loans, typical house, two children in public school. '
            f'Medicare figures follow Fidelity 2026 ($185,500 per individual over '
            f'retirement, excluding long-term care), modeled as $8,000/yr at 65 growing '
            f'2.5%/yr real. The long-term-care line is a rough expected-value allowance, '
            f'not a sourced estimate. Real 2026 dollars, net of tax.'
        )),
        ('base', f'base-{k}.scenario.json'),
        ('dimensions', [
            {'id': 'savings', 'name': 'Savings rate / lifestyle creep',
             'variants': savings_variants(h)},
            {'id': 'health', 'name': 'Retiree healthcare', 'variants': health_variants(h)},
            {'id': 'fixed', 'name': 'Other decisions (held fixed)', 'variants': [
                collections.OrderedDict([
                    ('id', 'standard'), ('name', 'Retire 65, standard loans, typical house, 2 kids public'),
                    ('events', fixed_events)])]},
        ]),
    ])
    with open(os.path.join(HERE, f'grid-{k}-health.json'), 'w') as f:
        json.dump(g, f, indent=2)
        f.write('\n')
    print(f'   grid-{k}-health.json: {len(SAVINGS_SHARES)*len(HEALTH)} sims')


def build(h):
    k = h['key']
    age = h['current_age']
    base = collections.OrderedDict([
        ('plancraft', 1),
        ('meta', {
            'name': h['label'],
            'description': (h['blurb'] + ' All figures are real 2026 dollars, net of '
                            'tax. Savings, student loans, housing and education are '
                            'grid dimensions.'),
            'anchorYear': ANCHOR,
        }),
        ('household', {
            'person1': {'currentAge': {'years': age}, 'retirementAge': {'years': 65},
                        'maxAge': {'years': 95}},
            'person2': {'currentAge': {'years': age}, 'retirementAge': {'years': 65},
                        'maxAge': {'years': 95}},
            'withdrawalStart': 'person1',
        }),
        ('portfolio', {'balance': h['portfolio']}),
        ('events', []),
        ('simulation', {
            'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}},
            'inflation': {'manual': 0.024},
            'sampling': {'type': 'monteCarlo', 'numRuns': 2000, 'seed': 1776},
            'legacy': 0,
        }),
    ])

    dims = [
        {'id': 'savings', 'name': 'Savings rate / lifestyle creep',
         'variants': savings_variants(h)},
        {'id': 'retire', 'name': 'Retirement age', 'variants': retirement_variants(h)},
        {'id': 'loans', 'name': 'Student loan payoff', 'variants': loan_variants(h)},
        {'id': 'housing', 'name': 'House size', 'variants': housing_variants(h)},
        {'id': 'education', 'name': 'Children and schooling',
         'variants': education_variants(h)},
    ]
    grid = collections.OrderedDict([
        ('plancraftGrid', 1),
        ('name', f'{h["label"]}: what actually moves the needle'),
        ('description', (
            f'{h["blurb"]} Ranks five recurring decisions by their effect on retirement '
            f'living standard. Savings figures are net investable savings before the '
            f'student loan, housing and education obligations modeled here as essential '
            f'expenses, so present-day discretionary consumption is net income minus '
            f'savings. {h["ss_note"]} Children are born 2027/2029/2031; 529 funding runs '
            f'birth to 18, private K-12 ages 5-18, the college top-up ages 18-22. '
            f'Housing is the annual cost increment over a modest house on a 30-year '
            f'mortgage from 2027. The metric is median first-year general (lifestyle) '
            f'retirement spending, which excludes earmarked essential expenses. '
            f'Investment costs live in the companion fees grid, because fee drag is a '
            f'return reduction and would collide with the return conditions. Because '
            f'house, schooling and loan payments compete with savings for the same net '
            f'income, some combinations are budget-infeasible; analyze.js reports '
            f'matched effect sizes over the feasible region. Real 2026 dollars, net of '
            f'tax; representative rather than anyone actual.'
        )),
        ('base', f'base-{k}.scenario.json'),
        ('dimensions', dims),
        ('conditions', CONDITIONS),
    ])

    fee_grid = collections.OrderedDict([
        ('plancraftGrid', 1),
        ('name', f'{h["label"]}: the cost of investment costs'),
        ('description', (
            f'Companion isolating fee drag for {h["label"]}, modeled as a permanent '
            f'reduction in expected return (5.0%/2.0% gross less the stated fee). '
            f'Crossed against savings rate and retirement age so the fee effect reads '
            f'against the two decisions known to dominate. Other decisions held at '
            f'standard loans, typical house, two children in public school.'
        )),
        ('base', f'base-{k}.scenario.json'),
        ('dimensions', [
            {'id': 'fees', 'name': 'Investment costs', 'variants': [
                collections.OrderedDict([
                    ('id', vid), ('name', name),
                    ('simulation', {'expectedReturns': {'fixed': {'stocks': s, 'bonds': b}}}),
                ]) for vid, (name, s, b) in FEES.items()]},
            {'id': 'savings', 'name': 'Savings rate / lifestyle creep',
             'variants': savings_variants(h)},
            {'id': 'retire', 'name': 'Retirement age', 'variants': retirement_variants(h)},
            {'id': 'fixed', 'name': 'Other decisions (held fixed)', 'variants': [
                collections.OrderedDict([
                    ('id', 'standard'),
                    ('name', 'Standard loans, typical house, 2 kids public'),
                    ('events', loan_variants(h)[1]['events']
                               + housing_variants(h)[1]['events']
                               + education_variants(h)[0]['events']),
                ])]},
        ]),
    ])

    # Constants analyze.js needs to reconstruct the budget constraint.
    params = collections.OrderedDict([
        ('key', k), ('label', h['label']),
        ('currentAge', age), ('netIncome', h['net_income']),
        ('portfolio', h['portfolio']),
        ('savings', {vid: [int(round(h['net_income'] * share, -3)), growth]
                     for vid, (_, share, growth) in SAVINGS_SHARES.items()}),
        ('loans', {vid: [py, yrs] for vid, (_, py, yrs) in h['loans'].items()}),
        ('housing', {vid: inc for vid, (_, inc) in h['housing'].items()}),
        ('education', {vid: [n, priv] for vid, (_, n, priv) in EDUCATION.items()}),
        ('retire', {f'r{a}': a for a in h['ss']}),
        ('kidBirth', KID_BIRTH), ('fivetwonine', FIVE_TWO_NINE_PER_MONTH * 12),
        ('privateK12', h['private_k12']), ('collegeTopUp', COLLEGE_TOPUP_PER_YEAR),
    ])

    for name, obj in [(f'base-{k}.scenario.json', base), (f'grid-{k}.json', grid),
                      (f'grid-{k}-fees.json', fee_grid), (f'params-{k}.json', params)]:
        with open(os.path.join(HERE, name), 'w') as f:
            json.dump(obj, f, indent=2)
            f.write('\n')
    n = 1
    for d in dims:
        n *= len(d['variants'])
    print(f'{h["label"]}')
    print(f'   net ${h["net_income"]:,}  portfolio ${h["portfolio"]:,}  age {age}')
    print(f'   savings variants: ' + ', '.join(
        f'{v}=${int(round(h["net_income"]*s, -3)):,}' for v, (_, s, _g) in SAVINGS_SHARES.items()))
    print(f'   grid-{k}.json: {n} combos x {len(CONDITIONS)} = {n*len(CONDITIONS)} sims')
    print(f'   description chars: {len(grid["description"])}\n')


for h in HOUSEHOLDS.values():
    build(h)
    build_health_grid(h)

# Household A previously lived in unsuffixed files; remove them so there is a
# single naming scheme.
for stale in ['base.scenario.json', 'grid.json', 'grid-fees.json']:
    p = os.path.join(HERE, stale)
    if os.path.exists(p):
        os.remove(p)
        print(f'removed stale {stale}')
