#!/usr/bin/env python3
"""Pass 2: the dollar answer, with a floor ladder.

Pass 1 ranked the levers against one fixed floor and reported percentage
points, which has two problems. Points compress badly at the top -- the gap
between 97% and 99% reads as small and is not -- and they are blind to
everything above the floor, which is how a $5M legacy managed to score as
SAFER than no legacy there: it suppressed spending by $2,032/month, preserved
the portfolio, and the metric had no way to charge for the spending given up.

So this pass sweeps the floor itself. Each combination is run against a
ladder of floors, and the reported answer is the highest floor it sustains at
90% confidence, found by interpolating where success crosses that line. That
is a number in dollars a month, comparable across levers, and it prices the
legacy honestly because committing to a bequest lowers the floor you can
promise yourself.

Six dimensions again, the schema's cap. Child cost is held at the middle
adder and the house at the $850,000 purchase, both having ranked below the
levers kept here.
"""
import collections, importlib.util, json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


L = _load('levers', os.path.join(HERE, 'levers.py'))
B, I = L.B, L.I

FLOORS = [8_000, 12_000, 16_000, 20_000, 24_000, 28_000]
CHILD_ADDER = L.CHILD_ADDER['mid'][1]

SIMONE = collections.OrderedDict([
    ('full', L.SIMONE['full']),
    ('p50p', L.SIMONE['p50p']),
    ('homet', L.SIMONE['homet']),
    ('homep', L.SIMONE['homep']),
])

# Parental support gets its own share axis here, because it is a negotiation
# with the sister rather than a fact, and pass 1 ranked it fourth of six --
# ahead of the child-cost adder and far ahead of the legacy.
PARENTS = collections.OrderedDict([
    ('none', ('No support needed', None, None, None, 0.0)),
    ('br50', ('Brazil care, half share', 'br',
              {2026: 'independent', 2030: 'home-care', 2034: 'nursing'}, None, 0.5)),
    ('us50', ('US care, half share', 'us',
              {2028: 'independent', 2032: 'assisted-one', 2036: 'nursing'},
              2033, 0.5)),
    ('us100', ('US care, we carry all of it', 'us',
               {2028: 'independent', 2032: 'assisted-one', 2036: 'nursing'},
               2033, 1.0)),
])

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Pass 2: the highest floor each choice can promise'),
    ('description', (
        'The same household against a ladder of retirement spending floors, so the '
        'answer comes out in dollars a month rather than percentage points. For '
        'each combination the analysis interpolates the highest floor sustained at '
        '90% confidence. This prices decisions that the fixed-floor pass could not: '
        'a legacy target suppresses spending and therefore looked SAFER there, '
        'because success measured only whether the floor held and never what was '
        'given up above it. Parental support carries a share axis, since it is a '
        'negotiation rather than a fact. Child living costs are held at the middle '
        'adder and the house at the $850,000 Cherry Hill purchase, both having '
        'ranked below the levers kept here. The FERS annuity is included throughout '
        'and retirement health cover is deliberately not modelled.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'floor', 'name': 'Spending floor', 'variants': [
            collections.OrderedDict([
                ('id', f'f{f // 1000}'), ('name', f'${f:,}/mo floor'),
                ('simulation', {'spendingFloor': f}),
            ]) for f in FLOORS]},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', B.retirement_income_events(a, True)
                 + B.house_events(B.HOUSES[L.HOUSE][1])
                 + L.child_living_events(CHILD_ADDER)),
            ]) for a in (55, 60, 65)]},
        {'id': 'simone', 'name': "Simone's career", 'variants': [
            collections.OrderedDict([('id', sid), ('name', name),
                                     ('events', L.simone_events(lvl, tmp))])
            for sid, (name, lvl, tmp) in SIMONE.items()]},
        {'id': 'school', 'name': 'Schooling', 'variants': [
            collections.OrderedDict([('id', sid), ('name', name),
                                     ('events', L.schooling_events(priv, col))])
            for sid, (name, priv, col) in L.SCHOOLING.items()]},
        {'id': 'parents', 'name': "Simone's parents", 'variants': [
            collections.OrderedDict([('id', pid), ('name', name),
                                     ('events', [] if path is None
                                      else L.care_events(path, sched, med, share))])
            for pid, (name, path, sched, med, share) in PARENTS.items()]},
        {'id': 'legacy', 'name': 'Legacy', 'variants': [
            collections.OrderedDict([('id', 'none'), ('name', 'No legacy'),
                                     ('simulation', {'legacy': 0})]),
            collections.OrderedDict([('id', 'm5'), ('name', 'Leave $5M real'),
                                     ('simulation', {'legacy': 5_000_000})]),
        ]},
    ]),
    ('conditions', L.CONDITIONS),
])

with open(os.path.join(HERE, 'grid-pass2.json'), 'w') as f:
    json.dump(grid, f, indent=2)
    f.write('\n')

if __name__ == '__main__':
    n = 1
    for d in grid['dimensions']:
        n *= len(d['variants'])
    print(f'{len(grid["dimensions"])} dimensions, {n} combinations x '
          f'{len(L.CONDITIONS)} conditions = {n * len(L.CONDITIONS)} simulations')
    print(f'floor ladder: ' + ', '.join(f'${f:,}' for f in FLOORS))
    print(f'description {len(grid["description"])} chars')
