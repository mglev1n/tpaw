#!/usr/bin/env python3
"""Supporting Simone's parents: US vs Brazil, and how the siblings split it.

Builds a grid over two dimensions that actually interact:

  support -- a care trajectory (where they live, how their needs escalate)
             crossed with this household's share of the net cost. Path and
             share have to live in one dimension because the grid composes
             dimensions by concatenating events, not by multiplying them.
  house   -- the live housing decision, so the question "how much house can
             we buy and still absorb this" is answered directly.

Timeline. The sister naturalizes in 2026 and petitions as a US citizen; a
parent is an immediate relative, so there is no annual cap and lawful
permanent residence lands around 2028. That starts the five-year clock, so
the Medicare buy-in opens around 2033. Care needs escalate on the schedules
below; the parents are 82 and 80 in 2026, so the streams run to 2040.

Everything here is this household's SHARE of the cost NET of the parents'
own pension. Dollar figures and their provenance are in parents_cost.py.
"""
import collections, importlib.util, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
LOC = os.path.join(os.path.dirname(HERE), 'location')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pc = _load('parents_cost', os.path.join(HERE, 'parents_cost.py'))
loc = _load('loc_build', os.path.join(LOC, 'build.py'))

ANCHOR, BUY_YEAR = 2026, 2027
CURRENT_AGE, MAX_AGE = 37, 95
LPR_YEAR, MEDICARE_YEAR, LAST_YEAR = 2028, 2033, 2040
PENSION = 30_000          # reportable; 142% FPL for a couple. Swept separately.

# Care trajectory: {first_year: care_level}. Applies until the next entry.
TRAJECTORIES = collections.OrderedDict([
    ('us-healthy',  ('us', {2028: 'independent'})),
    ('us-typical',  ('us', {2028: 'independent', 2032: 'assisted-one',
                            2036: 'nursing'})),
    ('us-severe',   ('us', {2028: 'independent', 2030: 'home-care',
                            2033: 'nursing'})),
    ('br-light',    ('br', {2026: 'independent', 2032: 'home-care'})),
    ('br-heavy',    ('br', {2026: 'independent', 2030: 'home-care',
                            2034: 'nursing'})),
])
SHARES = collections.OrderedDict([('third', 1 / 3), ('half', 0.5), ('all', 1.0)])
LABEL = {
    'us-healthy': 'US, stay independent',
    'us-typical': 'US, one in assisted 2032, both nursing 2036',
    'us-severe': 'US, home care 2030 then nursing 2033',
    'br-light': 'Brazil, home care from 2032',
    'br-heavy': 'Brazil, home care 2030 then nursing 2034',
}


def cost_stream(path, schedule, share):
    """This household's share of net annual cost, by calendar year."""
    out, care, start = {}, None, min(schedule)
    for year in range(start, LAST_YEAR + 1):
        if year in schedule:
            care = schedule[year]
        gross = pc.annual_cost(path, care, PENSION,
                               medicare_eligible=(path == 'us'
                                                  and year >= MEDICARE_YEAR))
        out[year] = max(0.0, gross['total'] - PENSION) * share
    return out


def segments(stream):
    """Collapse a year->amount map into piecewise-constant spans."""
    out, years = [], sorted(stream)
    i = 0
    while i < len(years):
        j = i
        while j + 1 < len(years) and abs(stream[years[j + 1]] - stream[years[i]]) < 1:
            j += 1
        if stream[years[i]] >= 1:
            out.append((years[i], years[j], round(stream[years[i]])))
        i = j + 1
    return out


def _variant(vid, name, path, sched, share):
    segs = segments(cost_stream(path, sched, share))
    return collections.OrderedDict([
        ('id', vid), ('name', name),
        ('events', [collections.OrderedDict([
            ('id', f'parents-{vid}-{k}'),
            ('label', f'Parental support {a}-{b}'),
            ('kind', 'expenseEssential'),
            ('amount', {'perYear': amt}),
            ('timing', {'from': {'calendarYear': a, 'month': 1},
                        'to': {'calendarYear': b, 'month': 12}}),
        ]) for k, (a, b, amt) in enumerate(segs)]),
    ])


DEFAULT_SHARE = 0.5     # one sibling, split down the middle


def support_variants():
    """Five care trajectories at an even two-way split, plus a no-support row.

    The dimension is capped at 8 variants, so the share sweep lives in its
    own grid (share_variants) rather than multiplying this one."""
    out = [collections.OrderedDict([
        ('id', 'none'), ('name', 'No support needed'), ('events', [])])]
    for tid, (path, sched) in TRAJECTORIES.items():
        out.append(_variant(tid, f'{LABEL[tid]} - we pay 50%', path, sched,
                            DEFAULT_SHARE))
    return out


def share_variants():
    """The two tail trajectories against every plausible sibling split.

    Simone's sister is a neurologist and her husband is in pharma, so their
    capacity to contribute is comparable or better; what is uncertain is
    willingness, distance (they are in Brookline), and who ends up doing the
    hands-on work rather than writing the cheque."""
    out = []
    for tid in ('us-severe', 'br-heavy'):
        path, sched = TRAJECTORIES[tid]
        for sid, share in SHARES.items():
            out.append(_variant(f'{tid}-{sid}',
                                f'{LABEL[tid]} - we pay {round(share * 100)}%',
                                path, sched, share))
    return out


def house_variants():
    """Reuse the verified location variants: the same 4BR at each price."""
    keep = {'ch-08003': 'Cherry Hill $655k (NJ)',
            'ml-wynnewood': 'Wynnewood $1.07M (PA)',
            'ml-brynmawr': 'Bryn Mawr $1.18M (PA)'}
    return [v for v in loc.location_variants() if v['id'] in keep]


SS = loc.SS[65]
base = collections.OrderedDict([
    ('plancraft', 1),
    ('meta', {'name': 'Parental support at $500k gross',
              'description': ('Two 37-year-olds, $500,000 gross, both working in '
                              'Philadelphia, no student debt, retiring at 65. Real '
                              '2026 dollars, net of tax.'),
              'anchorYear': ANCHOR}),
    ('household', {'person1': {'currentAge': {'years': CURRENT_AGE},
                               'retirementAge': {'years': 65},
                               'maxAge': {'years': MAX_AGE}},
                   'person2': {'currentAge': {'years': CURRENT_AGE},
                               'retirementAge': {'years': 65},
                               'maxAge': {'years': MAX_AGE}},
                   'withdrawalStart': 'person1'}),
    ('portfolio', {'balance': loc.PORTFOLIO_NOW + loc.MAX_DOWN}),
    ('events', [
        collections.OrderedDict([
            ('id', 'save'), ('label', 'Net investable savings'), ('kind', 'savings'),
            ('amount', {'perYear': int(round(loc.PA_NET * 0.31, -3))}),
            ('timing', {'from': {'named': 'now'},
                        'to': {'named': 'lastWorkingMonth', 'person': 'person1'}}),
        ]),
        collections.OrderedDict([
            ('id', 'ss-1'), ('label', 'Social Security (person 1, at 70)'),
            ('kind', 'retirementIncome'), ('amount', {'perMonth': SS[0]}),
            ('timing', {'from': {'age': {'person': 'person1', 'years': 70}},
                        'to': {'named': 'maxAge', 'person': 'person1'}}),
        ]),
        collections.OrderedDict([
            ('id', 'ss-2'), ('label', 'Social Security (person 2, at 70)'),
            ('kind', 'retirementIncome'), ('amount', {'perMonth': SS[1]}),
            ('timing', {'from': {'age': {'person': 'person2', 'years': 70}},
                        'to': {'named': 'maxAge', 'person': 'person2'}}),
        ]),
    ]),
    ('simulation', {'expectedReturns': {'fixed': {'stocks': 0.05, 'bonds': 0.02}},
                    'inflation': {'manual': 0.024},
                    'sampling': {'type': 'monteCarlo', 'numRuns': 2000, 'seed': 1776},
                    'legacy': 0}),
])

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Parental support: US vs Brazil, and who pays'),
    ('description', (
        'Two 37-year-olds, $500,000 gross, both working in Philadelphia, saving 31% '
        'of net, retiring at 65. Simone\'s parents are 82 and 80 in Brazil. Her '
        'sister naturalizes in 2026 and can petition for them as immediate '
        'relatives, so lawful permanent residence lands around 2028 and the '
        'Medicare buy-in opens around 2033 after the five-year residency bar. '
        'Before that they rely on the ACA marketplace, where a reportable pension '
        'of $30,000 puts them at 142% of the federal poverty level for a couple and '
        'premium tax credits cut the cost of benchmark silver coverage from about '
        '$28,000 a year to about $1,100. Below 100% FPL there is no credit at all as '
        'of plan year 2026 and above 400% the cliff has returned. Medicare never '
        'covers custodial long-term care, and Medicaid is blocked first by the '
        'five-year bar and then by sponsor deeming under the I-864 affidavit, so '
        'care is paid out of pocket either way -- at roughly four to five times the '
        'Brazilian price. Each variant is this household\'s share of the cost net of '
        'the parents\' own pension, split with Simone\'s sister and brother-in-law.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'support', 'name': 'Parents: where they age',
         'variants': support_variants()},
        {'id': 'house', 'name': 'House', 'variants': house_variants()},
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

share_grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Parental support: how much the sibling split matters'),
    ('description', (
        'The same household and the same two tail trajectories, against every '
        'plausible split with Simone\'s sister. Housing is held at the Cherry Hill '
        '$655k house so the split is the only thing moving. The point of the grid '
        'is the asymmetry: halving the share of a US nursing-care trajectory is '
        'worth far more than the entire difference between the three houses, while '
        'halving the share of a Brazilian one is worth almost nothing. Where the '
        'parents age determines whether the sibling negotiation is a financial '
        'conversation at all.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'support', 'name': 'Trajectory and our share',
         'variants': share_variants()},
        {'id': 'house', 'name': 'House',
         'variants': [v for v in loc.location_variants() if v['id'] == 'ch-08003']},
    ]),
    ('conditions', grid['conditions']),
])

for _n, _o in [('base.scenario.json', base), ('grid.json', grid),
               ('grid-share.json', share_grid)]:
    with open(os.path.join(HERE, _n), 'w') as f:
        json.dump(_o, f, indent=2)
        f.write('\n')

if __name__ == '__main__':
    for g in (grid, share_grid):
        n = len(g['dimensions'][0]['variants']) * len(g['dimensions'][1]['variants'])
        print(f'{g["name"]}: {n} combinations x {len(g["conditions"])} = '
              f'{n * len(g["conditions"])} simulations '
              f'({len(g["description"])} description chars)')
    print()
    print(f'{"trajectory":>38}{"2028":>9}{"2032":>9}{"2035":>9}{"2038":>9}'
          f'{"total":>12}')
    for tid, (path, sched) in TRAJECTORIES.items():
        s = cost_stream(path, sched, 1.0)
        tot = sum(s.values())
        print(f'{LABEL[tid]:>38}' + ''.join(
            f'{pc.usd(s.get(y, 0)):>9}' for y in (2028, 2032, 2035, 2038))
            + f'{pc.usd(tot):>12}')
    print('\nLifetime totals at 100% share; divide by 2 or 3 for a sibling split.')
