#!/usr/bin/env python3
"""Pass 1: rank every lever against a fixed floor.

Six dimensions, which is the schema's cap, and eight variants in the widest,
which is also the cap: 1,728 combinations. Too wide to read as a table, which
is the point -- this pass exists to find which levers move the answer, so
pass 2 can spend a floor ladder on those and ignore the rest.

WHAT CHANGED FROM build.py. Ordinary living costs now scale with household
size. Until now they sat flat at $8,000/month whether there were zero
children or two, with children adding only daycare, tuition and college --
which is not what a child costs. Food, clothing, activities, a larger car and
family travel are not tuition. OECD-modified equivalence (first adult 1.0,
second 0.5, each child 0.3) puts two children at home at about +$3,200/month
against that base, roughly $845,000 across the years they are at home, none
of which was modelled. It also reverses as they leave, which is why a
retirement floor should not be read off peak-family spending.

The adder enters as an essential expense rather than as reduced savings, so
that it composes with the Simone dimension: grid dimensions cannot see one
another, and savings has to belong to exactly one of them.
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
B = _load('build', os.path.join(HERE, 'build.py'))
pc = _load('parents_cost', os.path.join(os.path.dirname(HERE), 'parents',
                                        'parents_cost.py'))

usd = lambda v: '$' + format(round(v), ',')
ANCHOR = I.ANCHOR
KIDS = I.KIDS['birth_years']
AT_HOME_UNTIL = 17          # the college line takes over after this
STEP_DOWN_YEAR = 2031       # Simone turns 43
RETURN_YEAR = 2041          # if the step-down reverses
FLOOR = 12_000
HOUSE = 'ch-850k'

# --- Dimension 1: what a child costs in ordinary living ---------------------
CHILD_ADDER = collections.OrderedDict([
    ('lean', ('+$1,600/mo per child', 1_600)),
    ('mid', ('+$2,400/mo per child', 2_400)),
    ('rich', ('+$3,200/mo per child', 3_200)),
])


def child_living_events(per_month):
    """Phased by how many children are actually at home each year."""
    count = {}
    for birth in KIDS:
        for y in range(birth, birth + AT_HOME_UNTIL + 1):
            count[y] = count.get(y, 0) + 1
    out, years, i, k = [], sorted(count), 0, 0
    while i < len(years):
        j = i
        while j + 1 < len(years) and count[years[j + 1]] == count[years[i]]:
            j += 1
        out.append(B._ev(
            f'kidliving-{k}',
            f'Living costs for {count[years[i]]} child'
            f'{"ren" if count[years[i]] > 1 else ""} at home',
            'expenseEssential', {'perMonth': per_month * count[years[i]]},
            B._span(years[i], years[j])))
        k += 1
        i = j + 1
    return out


# --- Dimension 2: Simone's career ------------------------------------------
FELLOW_Y, FELLOW_M = I.SIMONE_FELLOW_END
FULL = I.SIMONE_ATTENDING_GROSS


def _save(vid, label, gross, timing):
    net = CF.net_income(I.MICHAEL_GROSS + gross)
    return B._ev(vid, label, 'savings',
                 {'perYear': max(0, round(net - B.LIVING))}, timing)


def simone_events(level, temporary):
    """Fellow, then full-time, then a step-down that may or may not reverse."""
    out = [
        _save('save-1', 'Savings while Simone is a fellow',
              I.SIMONE_FELLOW_GROSS,
              {'from': {'named': 'now'},
               'to': {'calendarYear': FELLOW_Y, 'month': FELLOW_M}}),
    ]
    if level == FULL:
        out.append(_save('save-2', 'Savings, Simone full time', FULL,
                         {'from': {'calendarYear': FELLOW_Y, 'month': FELLOW_M + 1},
                          'to': {'named': 'lastWorkingMonth', 'person': 'person1'}}))
        return out
    out.append(_save('save-2', 'Savings, Simone full time', FULL,
                     {'from': {'calendarYear': FELLOW_Y, 'month': FELLOW_M + 1},
                      'to': {'calendarYear': STEP_DOWN_YEAR - 1, 'month': 12}}))
    if temporary:
        out.append(_save('save-3', 'Savings while Simone is stepped down', level,
                         B._span(STEP_DOWN_YEAR, RETURN_YEAR - 1)))
        out.append(_save('save-4', 'Savings after Simone returns full time', FULL,
                         {'from': {'calendarYear': RETURN_YEAR, 'month': 1},
                          'to': {'named': 'lastWorkingMonth', 'person': 'person1'}}))
    else:
        out.append(_save('save-3', 'Savings, Simone stepped down', level,
                         {'from': {'calendarYear': STEP_DOWN_YEAR, 'month': 1},
                          'to': {'named': 'lastWorkingMonth', 'person': 'person1'}}))
    return out


SIMONE = collections.OrderedDict([
    ('full', ('Full time throughout', FULL, False)),
    ('p75t', ('0.75 FTE 2031-40, then back', int(FULL * 0.75), True)),
    ('p50p', ('0.5 FTE from 2031, permanent', int(FULL * 0.5), False)),
    ('p50t', ('0.5 FTE 2031-40, then back', int(FULL * 0.5), True)),
    ('p25p', ('0.25 FTE from 2031, permanent', int(FULL * 0.25), False)),
    ('p25t', ('0.25 FTE 2031-40, then back', int(FULL * 0.25), True)),
    ('homep', ('Stay-at-home from 2031, permanent', 0, False)),
    ('homet', ('Stay-at-home 2031-40, then back', 0, True)),
])

# --- Dimension 3: schooling -------------------------------------------------
K12_PRIVATE = 35_000
COLLEGE_PUBLIC = 35_000      # in-state, all-in
COLLEGE_PRIVATE = 95_000     # private university, all-in, full freight
SCHOOLING = collections.OrderedDict([
    ('pub-pub', ('Public K-12, in-state college', False, COLLEGE_PUBLIC)),
    ('pub-priv', ('Public K-12, private college', False, COLLEGE_PRIVATE)),
    ('priv-pub', ('Private K-12, in-state college', True, COLLEGE_PUBLIC)),
    ('priv-priv', ('Private K-12, private college', True, COLLEGE_PRIVATE)),
])


def schooling_events(private_k12, college_per_year):
    out = []
    for n, birth in enumerate(KIDS, start=1):
        out.append(B._ev(f'daycare-{n}', f'Daycare, child {n}', 'expenseEssential',
                         {'perMonth': B.DAYCARE_PER_MONTH},
                         B._span(birth, birth + 4)))
        if private_k12:
            out.append(B._ev(f'k12-{n}', f'Private school, child {n}',
                             'expenseEssential', {'perYear': K12_PRIVATE},
                             B._span(birth + 5, birth + 17)))
        out.append(B._ev(f'college-{n}', f'College, child {n}', 'expenseEssential',
                         {'perYear': college_per_year},
                         B._span(birth + 18, birth + 21)))
    return out


# --- Dimension 4: parental support ------------------------------------------
def care_events(path, sched, medicare_year, share=0.5):
    rows, care = {}, None
    for year in range(min(sched), 2041):
        if year in sched:
            care = sched[year]
        gross = pc.annual_cost(path, care, B.PARENTS_PENSION,
                               medicare_eligible=(medicare_year is not None
                                                  and year >= medicare_year))
        rows[year] = max(0.0, gross['total'] - B.PARENTS_PENSION) * share
    out, years, i, k = [], sorted(rows), 0, 0
    while i < len(years):
        j = i
        while j + 1 < len(years) and abs(rows[years[j + 1]] - rows[years[i]]) < 1:
            j += 1
        if rows[years[i]] >= 1:
            out.append(B._ev(f'parents-{k}', f'Parental support {years[i]}-{years[j]}',
                             'expenseEssential', {'perYear': round(rows[years[i]])},
                             B._span(years[i], years[j])))
            k += 1
        i = j + 1
    return out


PARENTS = collections.OrderedDict([
    ('none', ('No support needed', None, None, None)),
    ('brazil', ('Brazil care, half share', 'br',
                {2026: 'independent', 2030: 'home-care', 2034: 'nursing'}, None)),
    ('us', ('US care, half share', 'us',
            {2028: 'independent', 2032: 'assisted-one', 2036: 'nursing'}, 2033)),
])

CONDITIONS = [c for c in B.CONDITIONS if c['id'] != 'optimistic'] + [
    {'id': 'severe', 'name': 'Severe (2%/0.5%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.02, 'bonds': 0.005}}}},
]

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Pass 1: which levers actually move the floor'),
    ('description', (
        'Six dimensions at a fixed $12,000 a month retirement floor, so every cell '
        'reports the probability that floor stayed affordable and the levers can be '
        'ranked by effect size. Ordinary living costs now scale with household '
        'size, which they did not before: children added only daycare, tuition and '
        'college, as though a child cost nothing else. The adder is swept rather '
        'than assumed, since it is a choice as much as a fact. House is held at the '
        '$850,000 Cherry Hill purchase and the FERS annuity is included throughout. '
        'Combinations whose peak essential expenses exceed the household\'s savings '
        'are unpayable rather than merely risky, and the analysis flags them '
        'separately instead of ranking them.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'childcost', 'name': 'Cost of a child at home', 'variants': [
            collections.OrderedDict([('id', cid), ('name', name),
                                     ('events', child_living_events(amt))])
            for cid, (name, amt) in CHILD_ADDER.items()]},
        {'id': 'simone', 'name': "Simone's career", 'variants': [
            collections.OrderedDict([('id', sid), ('name', name),
                                     ('events', simone_events(lvl, tmp))])
            for sid, (name, lvl, tmp) in SIMONE.items()]},
        {'id': 'school', 'name': 'Schooling', 'variants': [
            collections.OrderedDict([('id', sid), ('name', name),
                                     ('events', schooling_events(priv, col))])
            for sid, (name, priv, col) in SCHOOLING.items()]},
        {'id': 'parents', 'name': "Simone's parents", 'variants': [
            collections.OrderedDict([('id', pid), ('name', name),
                                     ('events', [] if path is None
                                      else care_events(path, sched, med))])
            for pid, (name, path, sched, med) in PARENTS.items()]},
        {'id': 'legacy', 'name': 'Legacy', 'variants': [
            collections.OrderedDict([('id', 'none'), ('name', 'No legacy'),
                                     ('simulation', {'legacy': 0,
                                                     'spendingFloor': FLOOR})]),
            collections.OrderedDict([('id', 'm5'), ('name', 'Leave $5M real'),
                                     ('simulation', {'legacy': 5_000_000,
                                                     'spendingFloor': FLOOR})]),
        ]},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', B.retirement_income_events(a, True)
                 + B.house_events(B.HOUSES[HOUSE][1])),
            ]) for a in (55, 60, 65)]},
    ]),
    ('conditions', CONDITIONS),
])

with open(os.path.join(HERE, 'grid-levers.json'), 'w') as f:
    json.dump(grid, f, indent=2)
    f.write('\n')

if __name__ == '__main__':
    n = 1
    for d in grid['dimensions']:
        n *= len(d['variants'])
    print(f'{len(grid["dimensions"])} dimensions, {n} combinations '
          f'x {len(CONDITIONS)} conditions = {n * len(CONDITIONS)} simulations')
    print(f'description {len(grid["description"])} chars\n')
    print('Child living-cost adder, phased by children at home:')
    for cid, (name, amt) in CHILD_ADDER.items():
        evs = child_living_events(amt)
        span = ', '.join(f"{e['timing']['from']['calendarYear']}-"
                         f"{e['timing']['to']['calendarYear']} "
                         f"{usd(e['amount']['perMonth'])}/mo" for e in evs)
        print(f'  {name:<24} {span}')
    print('\nSavings by Simone variant (once stepped down, before child costs):')
    for sid, (name, lvl, tmp) in SIMONE.items():
        net = CF.net_income(I.MICHAEL_GROSS + lvl)
        print(f'  {name:<38}{usd(net - B.LIVING):>12}/yr')
