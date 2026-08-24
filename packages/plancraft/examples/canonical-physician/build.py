#!/usr/bin/env python3
"""Generate the canonical high-income physician household and its decision grids.

This household is deliberately synthetic and representative rather than
anyone's actual finances, so the resulting effect-size table can be published
and reasoned about generically. Every figure is stated in real (inflation
adjusted) 2026 dollars, and every income figure is NET of tax -- the engine
models one portfolio and takes net contributions, so taxes are handled
upstream by construction.

Run: python3 build.py   (writes base.scenario.json, grid.json, grid-fees.json)
"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = 2026

# ---------------------------------------------------------------------------
# Household
# ---------------------------------------------------------------------------
# Two 35-year-olds, two years out of training. Household gross ~$410k
# (physician ~$325k + spouse ~$85k); ~$270k net after federal, state and
# payroll tax. Real income held flat: physician real compensation has been
# roughly flat over the last two decades, so this avoids flattering the model.
NET_INCOME = 270_000
PORTFOLIO_NOW = 150_000

# Savings figures below are NET INVESTABLE SAVINGS BEFORE the explicit
# obligations modeled as expenses (student loans, incremental housing,
# education). Present-day discretionary consumption is therefore
#   NET_INCOME - savings - loans - housing - education
# which is what the lifestyle-creep trade-off is measured against.
SAVINGS = {
    'hyper': ('Hyper-saver (41% of net)', 110_000, 0.0),
    'high': ('High (31%)', 85_000, 0.0),
    'moderate': ('Moderate (23%)', 62_000, 0.0),
    'creep': ('Creeping (31% falling 2%/yr)', 85_000, -2.0),
}

# Social Security, claimed at 70, scaled down for shorter earnings records at
# earlier retirement ages. A physician who works to 65 approaches but does not
# reach 35 years of maximum-taxable earnings.
SS = {  # retirement age -> (physician $/mo, spouse $/mo)
    55: (3400, 2100),
    60: (3800, 2350),
    65: (4200, 2600),
    70: (4400, 2700),
}

# Student loans: ~$215k remaining at 35, 6.5%. Faster payoff costs more per
# year but far less in total interest.
LOANS = {
    'aggressive': ('Aggressive (5 yr)', 48_000, 5),
    'standard': ('Standard (10 yr)', 29_000, 10),
    'idr': ('Income-driven (20 yr)', 19_000, 20),
}

# Housing modeled as the annual cost INCREMENT over a modest house already
# inside baseline consumption, carried for a 30-year mortgage from 2027.
HOUSING = {
    'modest': ('Modest (~$550k)', 0),
    'typical': ('Typical (~$850k)', 14_000),
    'doctor': ('Doctor house (~$1.3M)', 30_000),
}

# Children born 2027 / 2029 / 2031. 529 funding runs birth to 18; private
# K-12 runs ages 5-18; the college top-up runs ages 18-22 on top of the 529.
EDUCATION = {
    'two-public': ('2 kids, public school', 2, False),
    'two-private': ('2 kids, private K-12 + college', 2, True),
    'three-public': ('3 kids, public school', 3, False),
}
KID_BIRTH = [2027, 2029, 2031]
FIVE_TWO_NINE_PER_MONTH = 500
PRIVATE_K12_PER_YEAR = 30_000
COLLEGE_TOPUP_PER_YEAR = 25_000


def event(id_, label, kind, amount, timing, growth=None):
    e = collections.OrderedDict(
        [('id', id_), ('label', label), ('kind', kind), ('amount', amount)]
    )
    if growth:
        e['growth'] = {'annualPercent': growth}
    e['timing'] = timing
    return e


def span(from_year, to_year, from_month=1, to_month=12):
    return {
        'from': {'calendarYear': from_year, 'month': from_month},
        'to': {'calendarYear': to_year, 'month': to_month},
    }


# ---------------------------------------------------------------------------
# Base scenario
# ---------------------------------------------------------------------------
base = collections.OrderedDict([
    ('plancraft', 1),
    ('meta', {
        'name': 'Canonical high-income physician household',
        'description': (
            'Synthetic, representative household used to rank financial decisions by '
            'effect size. Two 35-year-olds, two years out of training; household gross '
            '~$410k, ~$270,000 net; $150,000 invested; real income held flat. All '
            'figures are real 2026 dollars, net of tax. Savings, student loans, housing '
            'and education are grid dimensions.'
        ),
        'anchorYear': ANCHOR,
    }),
    ('household', {
        'person1': {'currentAge': {'years': 35}, 'retirementAge': {'years': 65},
                    'maxAge': {'years': 95}},
        'person2': {'currentAge': {'years': 35}, 'retirementAge': {'years': 65},
                    'maxAge': {'years': 95}},
        'withdrawalStart': 'person1',
    }),
    ('portfolio', {'balance': PORTFOLIO_NOW}),
    # Savings and Social Security are supplied by the grid dimensions, since
    # both depend on the savings-rate and retirement-age choices.
    ('events', []),
    ('simulation', {
        'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}},
        'inflation': {'manual': 0.024},
        'sampling': {'type': 'monteCarlo', 'numRuns': 2000, 'seed': 1776},
        'legacy': 0,
    }),
])


def savings_variants():
    out = []
    for vid, (name, amount, growth) in SAVINGS.items():
        out.append(collections.OrderedDict([
            ('id', vid), ('name', name),
            ('events', [event(
                'save', 'Net investable savings', 'savings',
                {'perYear': amount},
                {'from': {'named': 'now'},
                 'to': {'named': 'lastWorkingMonth', 'person': 'person1'}},
                growth=growth or None,
            )]),
        ]))
    return out


def retirement_variants():
    out = []
    for age, (phys, spouse) in SS.items():
        out.append(collections.OrderedDict([
            ('id', f'r{age}'), ('name', f'Retire at {age}'),
            ('household', {'person1': {'retirementAge': {'years': age}},
                           'person2': {'retirementAge': {'years': age}}}),
            ('events', [
                event('ss-1', 'Social Security (physician, at 70)', 'retirementIncome',
                      {'perMonth': phys},
                      {'from': {'age': {'person': 'person1', 'years': 70}},
                       'to': {'named': 'maxAge', 'person': 'person1'}}),
                event('ss-2', 'Social Security (spouse, at 70)', 'retirementIncome',
                      {'perMonth': spouse},
                      {'from': {'age': {'person': 'person2', 'years': 70}},
                       'to': {'named': 'maxAge', 'person': 'person2'}}),
            ]),
        ]))
    return out


def loan_variants():
    return [collections.OrderedDict([
        ('id', vid), ('name', name),
        ('events', [event('loans', 'Student loan payments', 'expenseEssential',
                          {'perYear': per_year},
                          span(ANCHOR, ANCHOR + years - 1))]),
    ]) for vid, (name, per_year, years) in LOANS.items()]


def housing_variants():
    out = []
    for vid, (name, increment) in HOUSING.items():
        events = []
        if increment:
            events.append(event('housing', 'Housing cost above baseline',
                                'expenseEssential', {'perYear': increment},
                                span(2027, 2056)))
        out.append(collections.OrderedDict([('id', vid), ('name', name),
                                            ('events', events)]))
    return out


def education_variants():
    out = []
    for vid, (name, n_kids, private) in EDUCATION.items():
        events = []
        for i in range(n_kids):
            born = KID_BIRTH[i]
            events.append(event(
                f'c529-{i+1}', f'529 (child {i+1})', 'expenseEssential',
                {'perMonth': FIVE_TWO_NINE_PER_MONTH}, span(born, born + 18)))
            if private:
                events.append(event(
                    f'k12-{i+1}', f'Private K-12 (child {i+1})', 'expenseEssential',
                    {'perYear': PRIVATE_K12_PER_YEAR},
                    span(born + 5, born + 18, from_month=9, to_month=6)))
                events.append(event(
                    f'college-{i+1}', f'College top-up (child {i+1})',
                    'expenseEssential', {'perYear': COLLEGE_TOPUP_PER_YEAR},
                    span(born + 18, born + 22, from_month=9, to_month=6)))
        out.append(collections.OrderedDict([('id', vid), ('name', name),
                                            ('events', events)]))
    return out


CONDITIONS = [
    {'id': 'pessimistic', 'name': 'Pessimistic (3.5%/1.5%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.035, 'bonds': 0.015}}}},
    {'id': 'base-returns', 'name': 'Base (5%/2%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}}}},
    {'id': 'optimistic', 'name': 'Optimistic (6.5%/3%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.065, 'bonds': 0.03}}}},
]

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Canonical physician household: what actually moves the needle'),
    ('description', (
        'Ranks five recurring high-income-household decisions by their effect on '
        'retirement living standard, for a synthetic two-physician-income household '
        '(both 35, ~$270,000 net, $150,000 invested, real income flat). Savings figures '
        'are net investable savings before the student loan, housing and education '
        'obligations modeled here as essential expenses, so present-day discretionary '
        'consumption is $270,000 minus savings minus those obligations. Social Security '
        'is claimed at 70 and scaled down at earlier retirement ages for the shorter '
        'earnings record. Children are born 2027/2029/2031; 529 funding runs birth to '
        '18, private K-12 ages 5-18, the college top-up ages 18-22. Housing is modeled '
        'as the annual cost increment over a modest house, carried on a 30-year '
        'mortgage from 2027. The reported metric is median first-year general '
        '(lifestyle) retirement spending, which excludes earmarked essential expenses, '
        'so a dimension only moves it by changing what is left over. Investment costs '
        'are handled in the companion grid-fees.json, because fee drag is expressed as '
        'a return reduction and would collide with the return conditions here. All '
        'figures real 2026 dollars, net of tax; the household is representative rather '
        'than anyone actual.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'savings', 'name': 'Savings rate / lifestyle creep',
         'variants': savings_variants()},
        {'id': 'retire', 'name': 'Retirement age', 'variants': retirement_variants()},
        {'id': 'loans', 'name': 'Student loan payoff', 'variants': loan_variants()},
        {'id': 'housing', 'name': 'House size', 'variants': housing_variants()},
        {'id': 'education', 'name': 'Children and schooling',
         'variants': education_variants()},
    ]),
    ('conditions', CONDITIONS),
])

# ---------------------------------------------------------------------------
# Companion grid: investment costs.
# ---------------------------------------------------------------------------
# Fee drag is a permanent reduction in realized return, so it is expressed
# through expectedReturns -- which is also how the return conditions are
# expressed. Running it as its own grid at a single return environment keeps
# the two from overwriting each other.
FEES = {
    'diy': ('DIY index (0.05%)', 0.0495, 0.0195),
    'lowcost': ('Low-cost advisor (0.40%)', 0.046, 0.016),
    'typical': ('Typical AUM (0.75%)', 0.0425, 0.0125),
    'full': ('Full-service AUM (1.10%)', 0.039, 0.009),
}

fee_grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Canonical physician household: the cost of investment costs'),
    ('description', (
        'Companion to grid.json isolating fee drag, which is modeled as a permanent '
        'reduction in expected return (5.0%/2.0% gross less the stated fee). Crossed '
        'against savings rate and retirement age so the fee effect can be read against '
        'the two decisions already known to dominate. Same canonical household; other '
        'decisions held at standard loans, typical house, two children in public '
        'school. Real 2026 dollars, net of tax.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'fees', 'name': 'Investment costs', 'variants': [
            collections.OrderedDict([
                ('id', vid), ('name', name),
                ('simulation', {'expectedReturns':
                                {'fixed': {'stocks': s, 'bonds': b}}}),
            ]) for vid, (name, s, b) in FEES.items()]},
        {'id': 'savings', 'name': 'Savings rate / lifestyle creep',
         'variants': savings_variants()},
        {'id': 'retire', 'name': 'Retirement age', 'variants': retirement_variants()},
        # Held fixed so the fee effect is read cleanly.
        {'id': 'fixed', 'name': 'Other decisions (held fixed)', 'variants': [
            collections.OrderedDict([
                ('id', 'standard'), ('name', 'Standard loans, typical house, 2 kids public'),
                ('events', loan_variants()[1]['events']
                           + housing_variants()[1]['events']
                           + education_variants()[0]['events']),
            ])]},
    ]),
])

for name, obj in [('base.scenario.json', base), ('grid.json', grid),
                  ('grid-fees.json', fee_grid)]:
    path = os.path.join(HERE, name)
    with open(path, 'w') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')
    print(f'wrote {name}')

n = 1
for d in grid['dimensions']:
    n *= len(d['variants'])
print(f'grid.json:      {n} combos x {len(CONDITIONS)} conditions = {n*len(CONDITIONS)} sims')
m = 1
for d in fee_grid['dimensions']:
    m *= len(d['variants'])
print(f'grid-fees.json: {m} combos x 1 condition = {m} sims')
print(f"description lengths: grid {len(grid['description'])}, "
      f"fees {len(fee_grid['description'])}")
