#!/usr/bin/env python3
"""The real household: Cherry Hill house price x schooling x parental support.

SAVINGS IS DERIVED, NOT SET. Earlier grids in this repository carried a
savings-rate dimension with variants like "31% of net", which quietly assumed
the rate was a choice held constant for thirty years. It is not: the rate is
whatever is left after tax, living costs, daycare, tuition, the mortgage and
whatever the parents need. So this grid emits, per year,

    savings = net income - living expenses

as the only contribution, and puts daycare, tuition, the house and parental
support in as essential expenses the engine draws from the portfolio. The
savings rate then falls out of the arithmetic and drops on its own when a
child arrives, when tuition starts, and when the mortgage steps up -- which
is what actually happens.

A consequence worth watching: a combination whose expenses exceed the
contribution is not merely a worse plan, it is one the household cannot fund
out of cash flow. The report flags those rather than ranking them.

Real figures live in inputs.local.json (gitignored). Everything else here is
either derived or an assumption flagged as one.
"""
import collections, importlib.util, json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


I = _load('inputs', os.path.join(HERE, 'inputs.py'))
CF = _load('cashflow', os.path.join(HERE, 'cashflow.py'))
loc = _load('loc', os.path.join(os.path.dirname(HERE), 'location', 'build.py'))
pc = _load('parents_cost', os.path.join(os.path.dirname(HERE), 'parents',
                                        'parents_cost.py'))

ANCHOR, BUY_YEAR = I.ANCHOR, 2027
AGE_M, AGE_S = I.AGE['michael'], I.AGE['simone']
MAX_AGE = I.MAX_AGE
RETIRE_BASE = 60

# --- Assumptions, all flagged ---------------------------------------------
DAYCARE_PER_MONTH = 2_000        # per child, birth to age 5
PRIVATE_K12_PER_YEAR = 35_000    # per child, ages 5-18, area independent schools
COLLEGE_PER_YEAR = 40_000        # per child, ages 18-22, both schooling branches
MORTGAGE_RATE, MORTGAGE_YEARS, DOWN_PCT = 0.065, 30, 0.20
PARENTS_SHARE = 0.5              # split with Simone's sister
PARENTS_PENSION = 30_000         # their reportable income; drives the ACA band


def usd(v):
    return '$' + format(round(v), ',')


# --- Savings, derived ------------------------------------------------------
LIVING = I.LIVING_EXPENSES_PER_MONTH * 12
FELLOW_END_Y, FELLOW_END_M = I.SIMONE_FELLOW_END
NET_PHASE1 = CF.net_income(I.MICHAEL_GROSS + I.SIMONE_FELLOW_GROSS)
NET_PHASE2 = CF.net_income(I.MICHAEL_GROSS + I.SIMONE_ATTENDING_GROSS)


def savings_events(lifestyle_multiple=1.0):
    living = LIVING * lifestyle_multiple
    return [
        _ev('save-1', 'Savings while Simone is a fellow', 'savings',
            {'perYear': max(0, round(NET_PHASE1 - living))},
            {'from': {'named': 'now'},
             'to': {'calendarYear': FELLOW_END_Y, 'month': FELLOW_END_M}}),
        _ev('save-2', 'Savings once Simone is an attending', 'savings',
            {'perYear': max(0, round(NET_PHASE2 - living))},
            {'from': {'calendarYear': FELLOW_END_Y, 'month': FELLOW_END_M + 1},
             'to': {'named': 'lastWorkingMonth', 'person': 'person1'}}),
    ]


def _ev(i, label, kind, amount, timing, nominal=False):
    e = collections.OrderedDict([('id', i), ('label', label), ('kind', kind),
                                 ('amount', amount)])
    if nominal:
        e['nominal'] = True
    e['timing'] = timing
    return e


def _span(y0, y1):
    return {'from': {'calendarYear': y0, 'month': 1},
            'to': {'calendarYear': y1, 'month': 12}}


# --- Children --------------------------------------------------------------
def child_events(private):
    out = []
    for n, birth in enumerate(I.KIDS['birth_years'], start=1):
        out.append(_ev(f'daycare-{n}', f'Daycare, child {n}', 'expenseEssential',
                       {'perMonth': DAYCARE_PER_MONTH}, _span(birth, birth + 4)))
        if private:
            out.append(_ev(f'k12-{n}', f'Private school, child {n}',
                           'expenseEssential', {'perYear': PRIVATE_K12_PER_YEAR},
                           _span(birth + 5, birth + 17)))
        out.append(_ev(f'college-{n}', f'College, child {n}', 'expenseEssential',
                       {'perYear': COLLEGE_PER_YEAR},
                       _span(birth + 18, birth + 21)))
    return out


# --- House -----------------------------------------------------------------
HOUSES = collections.OrderedDict([
    ('ch-655k', ('Cherry Hill $655k', 654_591)),
    ('ch-850k', ('Cherry Hill $850k', 850_000)),
    ('ch-1m', ('Cherry Hill $1.0M', 1_000_000)),
])
MAX_DOWN = max(p for _n, p in HOUSES.values()) * DOWN_PCT


def house_events(price):
    down = price * DOWN_PCT
    carry = price * (loc.PROPERTY_TAX['nj'] + loc.INSURANCE_PCT
                     + loc.MAINTENANCE_PCT)
    return [
        _ev('house-down', 'Down payment (20%)', 'expenseEssential',
            {'oneTime': round(down)},
            {'at': {'calendarYear': BUY_YEAR, 'month': 6}}),
        _ev('house-pi', 'Mortgage principal and interest', 'expenseEssential',
            {'perYear': round(loc.pmt(price - down))},
            _span(BUY_YEAR, BUY_YEAR + MORTGAGE_YEARS - 1), nominal=True),
        _ev('house-carry', 'Property tax, insurance, maintenance',
            'expenseEssential', {'perYear': round(carry)},
            {'from': {'calendarYear': BUY_YEAR, 'month': 1},
             'to': {'named': 'maxAge', 'person': 'person1'}}),
        _ev('rent', 'Rent until the purchase', 'expenseEssential',
            {'perMonth': I.CURRENT_RENT_PER_MONTH},
            {'from': {'named': 'now'},
             'to': {'calendarYear': BUY_YEAR, 'month': 5}}),
        _ev('nj-other', 'NJ auto insurance and sales tax premium',
            'expenseEssential',
            {'perYear': loc.NJ_AUTO_INSURANCE_EXTRA + loc.NJ_SALES_TAX_EXTRA},
            {'from': {'named': 'now'},
             'to': {'named': 'maxAge', 'person': 'person1'}}),
    ]


# --- Parents ---------------------------------------------------------------
TRAJECTORIES = collections.OrderedDict([
    ('none', ('none', 'No support needed', None, None)),
    ('brazil', ('br', 'Brazil, home care 2030 then nursing 2034',
                {2026: 'independent', 2030: 'home-care', 2034: 'nursing'}, None)),
    ('us', ('us', 'US, one assisted 2032, both nursing 2036',
            {2028: 'independent', 2032: 'assisted-one', 2036: 'nursing'}, 2033)),
])


def parent_events(path, sched, medicare_year):
    if sched is None:
        return []
    out, care = [], None
    rows = {}
    for year in range(min(sched), 2041):
        if year in sched:
            care = sched[year]
        gross = pc.annual_cost(path, care, PARENTS_PENSION,
                               medicare_eligible=(medicare_year is not None
                                                  and year >= medicare_year))
        rows[year] = max(0.0, gross['total'] - PARENTS_PENSION) * PARENTS_SHARE
    years, i, k = sorted(rows), 0, 0
    while i < len(years):
        j = i
        while j + 1 < len(years) and abs(rows[years[j + 1]] - rows[years[i]]) < 1:
            j += 1
        if rows[years[i]] >= 1:
            out.append(_ev(f'parents-{k}', f'Parental support {years[i]}-{years[j]}',
                           'expenseEssential', {'perYear': round(rows[years[i]])},
                           _span(years[i], years[j])))
            k += 1
        i = j + 1
    return out


# --- Retirement income -----------------------------------------------------
def fers_annuity(retire_age):
    """FERS basic annuity, prorated for the part-time tour.

    A part-time tour is computed on the FULL-TIME high-3 and then multiplied
    by the ratio of hours worked to full-time hours. Retiring before the MRA
    leaves a deferred annuity; at 62 with twenty years the multiplier rises
    to 1.1%."""
    f = I.FERS
    start_y, start_m = f['service_start']
    retire_year = ANCHOR + (retire_age - AGE_M)
    years = retire_year + 0.5 - (start_y + start_m / 12)
    age_at_start = 62 if retire_age < 62 else retire_age
    mult = 0.011 if (retire_age >= 62 and years >= 20) else 0.010
    annual = mult * f['full_time_high3'] * years * f['proration']
    return max(0.0, annual), age_at_start, years


def retirement_income_events(retire_age, with_fers):
    ss = I.SOCIAL_SECURITY
    out = [
        _ev('ss-1', 'Social Security (Michael, at 70)', 'retirementIncome',
            {'perMonth': ss['michael_at_70']},
            {'from': {'age': {'person': 'person1', 'years': 70}},
             'to': {'named': 'maxAge', 'person': 'person1'}}),
        _ev('ss-2', 'Social Security (Simone, at 70)', 'retirementIncome',
            {'perMonth': ss['simone_at_70']},
            {'from': {'age': {'person': 'person2', 'years': 70}},
             'to': {'named': 'maxAge', 'person': 'person2'}}),
    ]
    if with_fers:
        annual, start_age, _yrs = fers_annuity(retire_age)
        out.append(_ev('fers', 'FERS annuity (7/8 tour, prorated)',
                       'retirementIncome', {'perYear': round(annual)},
                       {'from': {'age': {'person': 'person1', 'years': start_age}},
                        'to': {'named': 'maxAge', 'person': 'person1'}}))
    return out


# --- Assembly --------------------------------------------------------------
def base_scenario(retire_age=RETIRE_BASE):
    return collections.OrderedDict([
        ('plancraft', 1),
        ('meta', {'name': 'Household 2026',
                  'description': ('Two physicians in Philadelphia buying in Cherry '
                                  'Hill in 2027. Savings is derived from income less '
                                  'tax less living costs, not set as a rate. Real '
                                  '2026 dollars, after tax.'),
                  'anchorYear': ANCHOR}),
        ('household', {
            'person1': {'currentAge': {'years': AGE_M},
                        'retirementAge': {'years': retire_age},
                        'maxAge': {'years': MAX_AGE}},
            'person2': {'currentAge': {'years': AGE_S},
                        'retirementAge': {'years': retire_age},
                        'maxAge': {'years': MAX_AGE}},
            'withdrawalStart': 'person1'}),
        ('portfolio', {'balance': round(I.simulated_portfolio())}),
        # Social Security and the annuity live on the retire dimension, since
        # both depend on the retirement age.
        ('events', savings_events()),
        ('simulation', {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}},
                        'inflation': {'manual': 0.024},
                        'sampling': {'type': 'monteCarlo', 'numRuns': 2000,
                                     'seed': 1776},
                        'legacy': 0}),
    ])


CONDITIONS = [
    {'id': 'pessimistic', 'name': 'Pessimistic (3.5%/1.5%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.035, 'bonds': 0.015}}}},
    {'id': 'base-returns', 'name': 'Base (5%/2%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}}}},
    {'id': 'optimistic', 'name': 'Optimistic (6.5%/3%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.065, 'bonds': 0.03}}}},
]

RETIRE_AGES = [55, 60, 65]

SCHOOLING = collections.OrderedDict([
    ('none', ('No children', None)),
    ('public', ('Two children, public school', False)),
    ('private', ('Two children, private K-12', True)),
])

main_grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'House price, schooling and parental support'),
    ('description', (
        'Two physicians in Philadelphia, buying in Cherry Hill in 2027. '
        'Savings is DERIVED here rather than set: the only contribution is '
        'net income less living costs, and daycare, tuition, the mortgage and '
        'parental support are essential expenses drawn from the portfolio, so the '
        'savings rate falls on its own as each one arrives. Children are assumed '
        'born in the two years shown, the first during the fellowship. Private '
        'school is priced at area independent schools; both schooling branches '
        'carry four years of college. Parental support is this household\'s half '
        'of the cost net of the parents\' own pension, on the trajectories from the '
        'parents example. The FERS annuity is included throughout, prorated for the '
        '7/8 tour. All amounts are real 2026 dollars after tax, the legacy target '
        'included; only mortgage principal and interest is nominal. Alongside the '
        'median, the report carries the 5th-percentile spending path, which is the '
        'downside that matters here: TPAW re-amortizes every month, so a bad return '
        'sequence shows up as spending that declines rather than as a plan that '
        'fails, and success probability saturates at 100%.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'house', 'name': 'House', 'variants': [
            collections.OrderedDict([('id', hid), ('name', name),
                                     ('events', house_events(price))])
            for hid, (name, price) in HOUSES.items()]},
        {'id': 'school', 'name': 'Children and schooling', 'variants': [
            collections.OrderedDict([('id', sid), ('name', name),
                                     ('events', [] if priv is None
                                      else child_events(priv))])
            for sid, (name, priv) in SCHOOLING.items()]},
        {'id': 'parents', 'name': "Simone's parents (our half)", 'variants': [
            collections.OrderedDict([('id', pid), ('name', name),
                                     ('events', parent_events(path, sched, med))])
            for pid, (path, name, sched, med) in TRAJECTORIES.items()]},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', retirement_income_events(a, True)),
            ]) for a in RETIRE_AGES]},
        {'id': 'legacy', 'name': 'Real legacy target', 'variants': [
            collections.OrderedDict([
                ('id', 'none'), ('name', 'No legacy'),
                ('simulation', {'legacy': 0})]),
            collections.OrderedDict([
                ('id', 'm5'), ('name', 'Leave $5M real'),
                ('simulation', {'legacy': 5_000_000})]),
        ]},
    ]),
    ('conditions', CONDITIONS),
])

LIFESTYLE = collections.OrderedDict([
    ('lean', ('Live on $8,000/mo', 1.0)),
    ('mid', ('Live on $10,000/mo', 10 / 8)),
    ('rich', ('Live on $12,000/mo', 12 / 8)),
])

fers_grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'FERS, retirement age and lifestyle'),
    ('description', (
        'Does the federal annuity change any decision? Held at the $850,000 Cherry '
        'Hill house with two children in public school and no parental support, so '
        'only these three move. The tour is 7/8 and part-time service is prorated '
        'in the FERS formula: the annuity is computed on the full-time high-3 and '
        'multiplied by the ratio of hours worked to full-time hours. Retiring '
        'before the minimum retirement age of 57 leaves a deferred annuity that '
        'starts at 62; at 62 with twenty years of service the multiplier rises from '
        '1.0% to 1.1%. Health insurance in retirement is deliberately not modelled. '
        'The lifestyle rows raise living costs against a fixed income, which is how '
        'the savings rate actually falls.'
    )),
    ('base', 'base.scenario.json'),
    # Dimension ORDER matters: variants are applied left to right and
    # excludeEventIds only sees what earlier dimensions have already added, so
    # the fers dimension has to come after the retire dimension that adds the
    # annuity.
    ('dimensions', [
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', retirement_income_events(a, True)),
            ]) for a in RETIRE_AGES]},
        {'id': 'lifestyle', 'name': 'Living costs', 'variants': [
            collections.OrderedDict([('id', lid), ('name', name),
                                     ('events', savings_events(mult))])
            for lid, (name, mult) in LIFESTYLE.items()]},
        # Removes the annuity rather than adding it: the amount depends on the
        # retirement age, so the retire dimension has to carry it.
        {'id': 'fers', 'name': 'Federal annuity', 'variants': [
            collections.OrderedDict([
                ('id', 'without'), ('name', 'Social Security only'),
                ('excludeEventIds', ['fers']),
                ('events', house_events(HOUSES['ch-850k'][1]) + child_events(False))]),
            collections.OrderedDict([
                ('id', 'with'), ('name', 'With FERS annuity'),
                ('events', house_events(HOUSES['ch-850k'][1]) + child_events(False))]),
        ]},
    ]),
    ('conditions', CONDITIONS),
])

for _n, _o in [('base.scenario.json', base_scenario()),
               ('grid.json', main_grid), ('grid-fers.json', fers_grid)]:
    with open(os.path.join(HERE, _n), 'w') as f:
        json.dump(_o, f, indent=2)
        f.write('\n')

if __name__ == '__main__':
    print(f'portfolio {usd(I.simulated_portfolio())}   living {usd(LIVING)}/yr')
    print(f'savings while fellow    {usd(NET_PHASE1 - LIVING)}/yr  '
          f'({(NET_PHASE1 - LIVING) / NET_PHASE1:.0%} of net)')
    print(f'savings once attending  {usd(NET_PHASE2 - LIVING)}/yr  '
          f'({(NET_PHASE2 - LIVING) / NET_PHASE2:.0%} of net)')
    print(f'\nFERS (7/8 tour, high-3 {usd(I.FERS["full_time_high3"])}, '
          f'proration {I.FERS["proration"]}):')
    for a in RETIRE_AGES:
        amt, start, yrs = fers_annuity(a)
        print(f'  retire {a}: {yrs:.1f} yrs service -> {usd(amt)}/yr from age {start}')
    print('\nPeak annual essential expenses by combination (main grid):')
    for hid, (hname, price) in HOUSES.items():
        for sid, (sname, priv) in SCHOOLING.items():
            evs = house_events(price) + ([] if priv is None else child_events(priv))
            peak = {}
            for e in evs:
                a = e['amount']
                amt = a.get('perYear', a.get('perMonth', 0) * 12)
                t = e['timing']
                if 'at' in t or 'calendarYear' not in t.get('from', {}):
                    continue
                y1 = t['to'].get('calendarYear', 2085)
                for y in range(t['from']['calendarYear'], min(y1, 2060) + 1):
                    peak[y] = peak.get(y, 0) + amt
            top = max(peak.values()) if peak else 0
            flag = '  <-- exceeds savings' if top > NET_PHASE2 - LIVING else ''
            print(f'  {hname:<20} {sname:<28} {usd(top):>10}{flag}')
    for g in (main_grid, fers_grid):
        n = 1
        for d in g['dimensions']:
            n *= len(d['variants'])
        print(f'\n{g["name"]}: {n} x {len(g["conditions"])} = {n * len(g["conditions"])} sims'
              f'  ({len(g["description"])} desc chars)')
