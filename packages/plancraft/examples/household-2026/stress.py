#!/usr/bin/env python3
"""Reverse stress test: what would it actually take to break the plan?

WHY SUCCESS PROBABILITY HAS BEEN USELESS SO FAR. TPAW re-amortizes every
month, so a bad decade shows up as spending that declines, never as a plan
that fails. Every cell of every grid in this example reads 100%. That is not
reassurance, it is the metric declining to answer: a plan that "succeeds" at
$3,000/month has not succeeded at anything.

SETTING A FLOOR FIXES IT. With simulation.spendingFloor set, the engine
stops amortizing below the floor and holds spending there instead
(general = max(general, floor) once withdrawals start). The portfolio can
then deplete, and successProbability becomes a real question with a real
answer: GIVEN THAT WE REFUSE TO LIVE ON LESS THAN $X A MONTH, how likely is
that refusal to be affordable? That is the number this file produces.

Note the floor changes behaviour, not just measurement: holding spending up
in a bad sequence spends the portfolio faster than flexing would. So a floor
run is a different plan, and its median spending differs from the no-floor
run. Both are reported.

TWO FLOORS, NOT ONE. They answer different questions and conflating them is
how people end up either frightened or complacent:
  - the STRUCTURAL floor is the level below which something has to be sold,
    cancelled or asked for -- the house, the legacy, help from the children;
  - the COMFORT floor is the level below which the retirement is simply
    disappointing. Dipping under it is a bad outcome, not a catastrophe.
House carrying costs, parental support and healthcare are modelled as
essential expenses elsewhere, so both floors are lifestyle spending ON TOP
of those, not total outgoings.
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

# --- The floors ------------------------------------------------------------
# Derived from what they spend now, not invented. Current outgoings are
# $8,000/month INCLUDING $2,800 of rent, so non-housing living runs about
# $5,200. In retirement the house is modelled separately, so the comparable
# lifestyle figure is that $5,200 plus what retirement adds: Medicare parts
# B and D with a supplement for two runs $1,500-2,000/month real at 65+, and
# the years a working couple spends at work are the years a retired couple
# spends spending.
FLOORS = collections.OrderedDict([
    ('none', ('No floor (spending flexes freely)', None)),
    ('f8', ('Structural floor $8,000/mo', 8_000)),
    ('f12', ('Comfort floor $12,000/mo', 12_000)),
    ('f16', ('Generous floor $16,000/mo', 16_000)),
])

# --- The stressors ---------------------------------------------------------
SIMONE_PART_TIME = 150_000     # 0.6 FTE attending instead of $250,000
CREEP_PER_MONTH = 12_000       # living costs, against $8,000 modelled


def savings_for(attending_gross, living_per_month):
    living = living_per_month * 12
    net1 = CF.net_income(I.MICHAEL_GROSS + I.SIMONE_FELLOW_GROSS)
    net2 = CF.net_income(I.MICHAEL_GROSS + attending_gross)
    fy, fm = I.SIMONE_FELLOW_END
    return [
        B._ev('save-1', 'Savings while Simone is a fellow', 'savings',
              {'perYear': max(0, round(net1 - living))},
              {'from': {'named': 'now'},
               'to': {'calendarYear': fy, 'month': fm}}),
        B._ev('save-2', 'Savings once Simone is an attending', 'savings',
              {'perYear': max(0, round(net2 - living))},
              {'from': {'calendarYear': fy, 'month': fm + 1},
               'to': {'named': 'lastWorkingMonth', 'person': 'person1'}}),
    ]


def severe_care_events():
    """US nursing-home trajectory, and this household carries all of it --
    the sister cannot or will not contribute."""
    sched = {2028: 'independent', 2030: 'home-care', 2033: 'nursing'}
    rows, care = {}, None
    for year in range(2028, 2041):
        if year in sched:
            care = sched[year]
        gross = pc.annual_cost('us', care, B.PARENTS_PENSION,
                               medicare_eligible=(year >= 2033))
        rows[year] = max(0.0, gross['total'] - B.PARENTS_PENSION)
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


def stress_variant(vid, name, *, living=8_000, attending=250_000,
                   max_age=None, care=False, private=False):
    v = collections.OrderedDict([('id', vid), ('name', name)])
    if max_age:
        v['household'] = {'person1': {'maxAge': {'years': max_age}},
                          'person2': {'maxAge': {'years': max_age}}}
    events = savings_for(attending, living)
    events += B.house_events(B.HOUSES['ch-850k'][1])
    events += B.child_events(private)
    if care:
        events += severe_care_events()
    v['events'] = events
    return v


STRESSES = [
    stress_variant('base', 'As planned'),
    stress_variant('creep', 'Lifestyle creep to $12,000/mo', living=CREEP_PER_MONTH),
    stress_variant('simone', 'Simone at 0.6 FTE', attending=SIMONE_PART_TIME),
    stress_variant('long', 'Both live to 100', max_age=100),
    stress_variant('care', 'US nursing care, we pay all of it', care=True),
    stress_variant('private', 'Private school throughout', private=True),
    stress_variant('creep-simone', 'Creep AND Simone at 0.6 FTE',
                   living=CREEP_PER_MONTH, attending=SIMONE_PART_TIME),
    stress_variant('all', 'Everything at once', living=CREEP_PER_MONTH,
                   attending=SIMONE_PART_TIME, max_age=100, care=True,
                   private=True),
]

CONDITIONS = B.CONDITIONS + [
    {'id': 'severe', 'name': 'Severe (2%/0.5%)',
     'simulation': {'expectedReturns': {'fixed': {'stocks': 0.02, 'bonds': 0.005}}}},
]

grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'What would it take to break the plan?'),
    ('description', (
        'A reverse stress test. Every other grid here reports 100% success, because '
        'TPAW re-amortizes every month and a bad decade shows up as spending that '
        'declines rather than a plan that fails -- so success probability declines '
        'to answer the question. Setting a spending floor restores it: the engine '
        'holds spending at the floor instead of flexing below it, the portfolio can '
        'then deplete, and success becomes "given that we refuse to live on less '
        'than this, how likely is that refusal to be affordable". The floor is '
        'lifestyle spending on top of the house, parental support and healthcare, '
        'which are modelled as essential expenses. Held at the $850,000 Cherry Hill '
        'house with retirement at 60 varied alongside. A fourth return condition, '
        'severe, is added below the pessimistic one.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'stress', 'name': 'What goes wrong', 'variants': STRESSES},
        {'id': 'floor', 'name': 'Spending floor', 'variants': [
            collections.OrderedDict([
                ('id', fid), ('name', name),
                ('simulation', {} if amt is None else {'spendingFloor': amt}),
            ]) for fid, (name, amt) in FLOORS.items()]},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', B.retirement_income_events(a, True)),
            ]) for a in (55, 60, 65)]},
    ]),
    ('conditions', CONDITIONS),
])

with open(os.path.join(HERE, 'grid-stress.json'), 'w') as f:
    json.dump(grid, f, indent=2)
    f.write('\n')

if __name__ == '__main__':
    n = 1
    for d in grid['dimensions']:
        n *= len(d['variants'])
    print(f'{n} combinations x {len(CONDITIONS)} conditions = {n * len(CONDITIONS)} sims')
    print(f'description {len(grid["description"])} chars\n')
    print('FEASIBILITY: a variant whose peak essential expenses exceed savings is')
    print('not a stressed plan but an unpayable one, and reads 0% for an accounting')
    print('reason rather than a market one.\n')
    print(f"{'stress variant':<34}{'saves/yr':>12}{'peak essential/yr':>22}")
    for v in STRESSES:
        sav = max(e['amount']['perYear'] for e in v['events']
                  if e['kind'] == 'savings')
        peak = {}
        for e in v['events']:
            if e['kind'] != 'expenseEssential':
                continue
            a = e['amount']
            amt = a.get('perYear', a.get('perMonth', 0) * 12)
            t = e['timing']
            if 'at' in t or 'calendarYear' not in t.get('from', {}):
                continue
            y1 = t['to'].get('calendarYear', 2060)
            for y in range(t['from']['calendarYear'], min(y1, 2060) + 1):
                peak[y] = peak.get(y, 0) + amt
        top = max(peak.values()) if peak else 0
        yr = max(peak, key=peak.get) if peak else 0
        flag = '  UNPAYABLE' if top > sav else ''
        print(f"{v['name']:<34}{usd(sav):>12}{usd(top) + f' ({yr})':>22}{flag}")

    print('\nSavings under each income/lifestyle pairing:')
    for label, att, liv in (('as planned', 250_000, 8_000),
                            ('creep to $12k/mo', 250_000, 12_000),
                            ('Simone 0.6 FTE', 150_000, 8_000),
                            ('both', 150_000, 12_000)):
        net2 = CF.net_income(I.MICHAEL_GROSS + att)
        print(f'  {label:<20} net {usd(net2)}  saves {usd(net2 - liv * 12)}/yr'
              f'  ({(net2 - liv * 12) / net2:.0%})')


# --- Recovery levers -------------------------------------------------------
# Two of the stress variants above are not stressed plans, they are unpayable
# ones: peak essential expenses exceed the household's entire savings, so the
# 0% is an accounting fact rather than a market outcome (see the feasibility
# table printed by __main__). Levers cannot rescue those; only changing the
# obligation can.
#
# So the recovery menu starts from a plan that is strained but payable --
# lifestyle crept to $12,000/mo, Simone at 0.6 FTE, private school throughout,
# both living to 100, and a Brazilian care trajectory split with the sister --
# and asks what each available lever is worth from there.
def brazil_care_events(share=0.5):
    sched = {2026: 'independent', 2030: 'home-care', 2034: 'nursing'}
    rows, care = {}, None
    for year in range(2026, 2041):
        if year in sched:
            care = sched[year]
        gross = pc.annual_cost('br', care, B.PARENTS_PENSION, medicare_eligible=False)
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


def lever(vid, name, *, living=CREEP_PER_MONTH, attending=SIMONE_PART_TIME,
          house='ch-850k', private=True, share=0.5, retire=60, floor=12_000):
    v = collections.OrderedDict([('id', vid), ('name', name)])
    v['household'] = {'person1': {'retirementAge': {'years': retire},
                                  'maxAge': {'years': 100}},
                      'person2': {'retirementAge': {'years': retire},
                                  'maxAge': {'years': 100}}}
    v['simulation'] = {'spendingFloor': floor}
    v['events'] = (savings_for(attending, living)
                   + B.house_events(B.HOUSES[house][1])
                   + B.child_events(private)
                   + brazil_care_events(share)
                   + B.retirement_income_events(retire, True))
    return v


LEVERS = [
    lever('none', 'Nothing changes'),
    lever('work-63', 'Work to 63 instead of 60', retire=63),
    lever('work-65', 'Work to 65 instead of 60', retire=65),
    lever('downsize', 'Buy the $655k house instead of $850k', house='ch-655k'),
    lever('public', 'Public school instead of private', private=False),
    lever('hold-line', 'Hold living costs at $8,000/mo', living=8_000),
    lever('share-33', "Sister carries two thirds of her parents' care", share=1 / 3),
    lever('lower-floor', 'Accept an $8,000/mo floor', floor=8_000),
]

recovery = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'Recovery levers from a strained plan'),
    ('description', (
        'One lever at a time, from a plan that is strained but payable: lifestyle '
        'crept to $12,000 a month, Simone at 0.6 FTE, private school throughout, '
        'both living to 100, and a Brazilian care trajectory split evenly with her '
        'sister, retiring at 60 against a $12,000 a month floor. Two of the '
        'scenarios in the stress grid are excluded here because they are not '
        'strained plans but unpayable ones -- peak essential expenses exceed the '
        'household\'s entire annual savings, so no lever rescues them and only '
        'changing the obligation does. Success is the probability the floor stayed '
        'affordable, so the levers are ranked by how much room each one buys.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [{'id': 'lever', 'name': 'Lever pulled', 'variants': LEVERS}]),
    ('conditions', CONDITIONS),
])

with open(os.path.join(HERE, 'grid-recovery.json'), 'w') as f:
    json.dump(recovery, f, indent=2)
    f.write('\n')
