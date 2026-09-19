#!/usr/bin/env python3
"""How much MORE can this household take on, and where does it break?

Rather than asking what private school or a parent's nursing home costs, this
asks the general question: how many dollars a year of ADDITIONAL obligation
can be absorbed while still promising a given retirement floor, funding a
given legacy, and retiring on a given date? Any specific commitment can then
be priced by looking its annual cost up on the same scale.

The burden is a flat real amount for twenty years, 2030 through 2049, which
is the window where child-rearing, schooling and a parent's care all fall.
For reference, on that scale:

    Brazilian care, half share            ~ $20k/yr
    Private K-12 for two                  ~ $70k/yr for 13 years
    US care, half share                   ~ $158k/yr at its peak
    Private college for two               ~ $190k/yr for 4 years
    US care, carried entirely             ~ $315k/yr at its peak

SOCIAL SECURITY AND FERS. Every result in this project so far has included
both, and they are large: Social Security at $4,200 and $3,400 a month from
age 70 is $91,200 a year, and the prorated FERS annuity runs $43,000 to
$72,000 depending on the retirement age. Together that is up to $163,000 a
year of guaranteed real income, and it is a substantial part of why the
earlier numbers looked as comfortable as they did. Those figures are also
estimates -- the Social Security ones have never been checked against an
earnings record. So income is a dimension here: both, Social Security only,
or neither. The last is the honest base case for planning at this distance,
since it asks whether the plan stands on the household's own savings.
"""
import collections, importlib.util, json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


L = _load('levers', os.path.join(HERE, 'levers.py'))
P2 = _load('pass2', os.path.join(HERE, 'pass2.py'))
HS = _load('housing', os.path.join(HERE, 'housing.py'))
B, I = L.B, L.I

BURDEN_FROM, BURDEN_TO = 2030, 2049
BURDENS = [0, 25_000, 50_000, 75_000, 100_000, 150_000, 200_000, 300_000]
CHILD_ADDER = L.CHILD_ADDER['mid'][1]


def income_events(retire_age, social_security, fers):
    """Retirement income, with each source separately switchable."""
    out = []
    if social_security:
        ss = I.SOCIAL_SECURITY
        out += [
            B._ev('ss-1', 'Social Security (Michael, at 70)', 'retirementIncome',
                  {'perMonth': ss['michael_at_70']},
                  {'from': {'age': {'person': 'person1', 'years': 70}},
                   'to': {'named': 'maxAge', 'person': 'person1'}}),
            B._ev('ss-2', 'Social Security (Simone, at 70)', 'retirementIncome',
                  {'perMonth': ss['simone_at_70']},
                  {'from': {'age': {'person': 'person2', 'years': 70}},
                   'to': {'named': 'maxAge', 'person': 'person2'}}),
        ]
    if fers:
        annual, start_age, _y = B.fers_annuity(retire_age)
        out.append(B._ev('fers', 'FERS annuity (7/8 tour, prorated)',
                         'retirementIncome', {'perYear': round(annual)},
                         {'from': {'age': {'person': 'person1',
                                           'years': start_age}},
                          'to': {'named': 'maxAge', 'person': 'person1'}}))
    return out


INCOME = collections.OrderedDict([
    ('neither', ('Own savings only', False, False)),
    ('ss', ('Social Security only', True, False)),
    ('both', ('Social Security and FERS', True, True)),
])

# Housing, schooling and child costs are the fixed backdrop; parental support
# is deliberately absent, because it is one of the things the burden axis is
# meant to price rather than assume.
BACKDROP = (HS.housing_events(850_000, 0.065, 30, 0.20)
            + L.simone_events(L.FULL, False))

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'How much more can we take on?'),
    ('description', (
        'Rather than pricing one commitment at a time, this sweeps a generic '
        'additional obligation -- a flat real amount every year from 2030 to 2049, '
        'the window where child-rearing, schooling and a parent\'s care all fall -- '
        'and asks how large it can be while still promising a retirement floor, '
        'funding a legacy and retiring on a given date. Any specific commitment is '
        'then priced by looking its annual cost up on the same scale. Social '
        'Security and the FERS annuity are a dimension rather than an assumption, '
        'because every earlier result in this project included both and they are '
        'worth up to $163,000 a year of guaranteed real income; the own-savings-only '
        'row is the honest base case at this distance. Backdrop: the $850,000 house '
        'at 30 years and 6.5%, Simone full time, public K-12 and in-state college, '
        'the middle child-cost adder, and no parental support, since that is one of '
        'the things the burden axis exists to price.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'floor', 'name': 'Spending floor', 'variants': [
            collections.OrderedDict([
                ('id', f'f{f // 1000}'), ('name', f'${f:,}/mo floor'),
                ('simulation', {'spendingFloor': f}),
            ]) for f in P2.FLOORS]},
        {'id': 'burden', 'name': 'Extra obligation, 2030-2049', 'variants': [
            collections.OrderedDict([
                ('id', f'b{b // 1000}'),
                ('name', 'None' if b == 0 else f'${b:,}/yr'),
                ('events', BACKDROP + ([] if b == 0 else [
                    B._ev('burden', f'Additional obligation (${b:,}/yr)',
                          'expenseEssential', {'perYear': b},
                          B._span(BURDEN_FROM, BURDEN_TO))])),
            ]) for b in BURDENS]},
        {'id': 'income', 'name': 'Guaranteed retirement income', 'variants': [
            collections.OrderedDict([('id', iid), ('name', name),
                                     ('events', [])])
            for iid, (name, _ss, _f) in INCOME.items()]},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
            ]) for a in (55, 60, 65)]},
        {'id': 'legacy', 'name': 'Legacy', 'variants': [
            collections.OrderedDict([('id', 'none'), ('name', 'No legacy'),
                                     ('simulation', {'legacy': 0})]),
            collections.OrderedDict([('id', 'm5'), ('name', 'Leave $5M real'),
                                     ('simulation', {'legacy': 5_000_000})]),
        ]},
    ]),
    ('conditions', L.CONDITIONS),
])

# Retirement income depends on BOTH the income switch and the retirement age,
# which are separate dimensions that cannot see one another. The retire
# dimension therefore emits the full-income events and the income dimension,
# applied after it, removes what that variant does not include -- an exclude
# can act on what an earlier dimension added, whereas an add cannot know the
# retirement age.
for _i, _a in enumerate((55, 60, 65)):
    grid['dimensions'][3]['variants'][_i]['events'] = income_events(_a, True, True)
for _v, (_iid, (_n, _ss, _fers)) in zip(grid['dimensions'][2]['variants'],
                                        INCOME.items()):
    drop = []
    if not _ss:
        drop += ['ss-1', 'ss-2']
    if not _fers:
        drop += ['fers']
    if drop:
        _v['excludeEventIds'] = drop
# ...which means the income dimension must come AFTER retire.
grid['dimensions'] = [grid['dimensions'][i] for i in (0, 1, 3, 2, 4)]

with open(os.path.join(HERE, 'grid-burden.json'), 'w') as f:
    json.dump(grid, f, indent=2)
    f.write('\n')

if __name__ == '__main__':
    n = 1
    for d in grid['dimensions']:
        n *= len(d['variants'])
    print(f'dimension order: {[d["id"] for d in grid["dimensions"]]}')
    print(f'{n} combinations x {len(L.CONDITIONS)} = {n * len(L.CONDITIONS)} sims')
    usd = lambda v: '$' + format(round(v), ',')
    print(f'\nGuaranteed income being switched on and off:')
    for a in (55, 60, 65):
        amt, start, yrs = B.fers_annuity(a)
        ss = (I.SOCIAL_SECURITY['michael_at_70']
              + I.SOCIAL_SECURITY['simone_at_70']) * 12
        print(f'  retire {a}: SS {usd(ss)}/yr from 70 + FERS {usd(amt)}/yr '
              f'from {start}  = {usd(ss + amt)}/yr')
