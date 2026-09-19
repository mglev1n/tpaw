#!/usr/bin/env python3
"""What does the house cost, in promised retirement floor?

Both earlier passes held housing at the $850,000 Cherry Hill purchase, so it
was the one large decision they could not price. It is really four separable
choices that do not behave alike:

  PRICE  buys more house and carries property tax, insurance and maintenance
         FOREVER -- unlike the mortgage, that part never amortizes away.
  RATE   touches only the interest, and only for the term. It is also the one
         input here the household does not choose.
  TERM   a 15-year note carries a lower rate and builds equity faster, at a
         much higher payment during exactly the years when daycare, tuition
         and the parents' care all land.
  DOWN   moves money from the portfolio into the house, lowering the payment
         by removing the balance that would have compounded. A real trade,
         and not obviously a good one.

WHY THESE ARE ONE DIMENSION AND NOT FOUR. The payment is a function of price,
rate, term and down payment jointly, but grid dimensions cannot see one
another -- an event merges by id, so a later dimension REPLACES rather than
adjusts. A full cross-product would be 48 variants against a cap of 8. So
this sweeps one change at a time from a common baseline ($850,000, 30 years
at 6.5%, 20% down), which isolates each effect and fits.
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
B, I, loc = L.B, L.I, L.B.loc

BUY_YEAR = 2027
CHILD_ADDER = L.CHILD_ADDER['mid'][1]
BASE_PRICE, BASE_RATE, BASE_TERM, BASE_DOWN = 850_000, 0.065, 30, 0.20

# (id, label, price, rate, term, down) -- one change at a time from baseline.
HOUSING = [
    ('p655', '$655k, 30yr 6.5%, 20% down', 654_591, 0.065, 30, 0.20),
    ('base', '$850k, 30yr 6.5%, 20% down', 850_000, 0.065, 30, 0.20),
    ('p1000', '$1.0M, 30yr 6.5%, 20% down', 1_000_000, 0.065, 30, 0.20),
    ('p1150', '$1.15M, 30yr 6.5%, 20% down', 1_150_000, 0.065, 30, 0.20),
    ('r50', '$850k, 30yr 5.0%, 20% down', 850_000, 0.050, 30, 0.20),
    ('r80', '$850k, 30yr 8.0%, 20% down', 850_000, 0.080, 30, 0.20),
    ('y15', '$850k, 15yr 5.9%, 20% down', 850_000, 0.059, 15, 0.20),
    ('d35', '$850k, 30yr 6.5%, 35% down', 850_000, 0.065, 30, 0.35),
]


def pmt(principal, rate, years):
    r = rate / 12
    return principal * r / (1 - (1 + r) ** -(years * 12)) * 12


def carry(price):
    return price * (loc.PROPERTY_TAX['nj'] + loc.INSURANCE_PCT
                    + loc.MAINTENANCE_PCT)


def housing_events(price, rate, term, down_pct):
    down = price * down_pct
    return [
        B._ev('house-down', f'Down payment ({down_pct:.0%})', 'expenseEssential',
              {'oneTime': round(down)},
              {'at': {'calendarYear': BUY_YEAR, 'month': 6}}),
        B._ev('house-pi', 'Mortgage principal and interest', 'expenseEssential',
              {'perYear': round(pmt(price - down, rate, term))},
              B._span(BUY_YEAR, BUY_YEAR + term - 1), nominal=True),
        B._ev('house-carry', 'Property tax, insurance, maintenance',
              'expenseEssential', {'perYear': round(carry(price))},
              {'from': {'calendarYear': BUY_YEAR, 'month': 1},
               'to': {'named': 'maxAge', 'person': 'person1'}}),
        B._ev('rent', 'Rent until the purchase', 'expenseEssential',
              {'perMonth': I.CURRENT_RENT_PER_MONTH},
              {'from': {'named': 'now'},
               'to': {'calendarYear': BUY_YEAR, 'month': 5}}),
        B._ev('nj-other', 'NJ auto insurance and sales tax premium',
              'expenseEssential',
              {'perYear': loc.NJ_AUTO_INSURANCE_EXTRA + loc.NJ_SALES_TAX_EXTRA},
              {'from': {'named': 'now'},
               'to': {'named': 'maxAge', 'person': 'person1'}}),
    ] + L.child_living_events(CHILD_ADDER) + L.schooling_events(
        False, L.COLLEGE_PUBLIC)


grid = collections.OrderedDict([
    ('plancraftGrid', 1),
    ('name', 'What the house costs in promised floor'),
    ('description', (
        'Housing was held at the $850,000 purchase through both earlier passes, so '
        'it was the one large decision they could not price. Price, interest rate, '
        'term and down payment are swept ONE AT A TIME from that baseline, because '
        'the payment depends on all four jointly while grid dimensions cannot see '
        'one another, and a full cross-product would need 48 variants against a cap '
        'of eight. Price carries property tax, insurance and maintenance for life; '
        'rate and term touch only the interest and only for the term; a larger down '
        'payment lowers the payment by removing invested balance. Public K-12 and '
        'in-state college, the middle child-cost adder, no legacy. The answer is '
        'the highest floor sustainable at 90% confidence.'
    )),
    ('base', 'base.scenario.json'),
    ('dimensions', [
        {'id': 'floor', 'name': 'Spending floor', 'variants': [
            collections.OrderedDict([
                ('id', f'f{f // 1000}'), ('name', f'${f:,}/mo floor'),
                ('simulation', {'spendingFloor': f}),
            ]) for f in P2.FLOORS]},
        {'id': 'housing', 'name': 'House and financing', 'variants': [
            collections.OrderedDict([
                ('id', hid), ('name', name),
                ('events', housing_events(price, rate, term, down)),
            ]) for hid, name, price, rate, term, down in HOUSING]},
        {'id': 'retire', 'name': 'Retirement age', 'variants': [
            collections.OrderedDict([
                ('id', f'r{a}'), ('name', f'Retire at {a}'),
                ('household', {'person1': {'retirementAge': {'years': a}},
                               'person2': {'retirementAge': {'years': a}}}),
                ('events', B.retirement_income_events(a, True)),
            ]) for a in (55, 60, 65)]},
        {'id': 'simone', 'name': "Simone's career", 'variants': [
            collections.OrderedDict([('id', sid), ('name', L.SIMONE[sid][0]),
                                     ('events', L.simone_events(L.SIMONE[sid][1],
                                                                L.SIMONE[sid][2]))])
            for sid in ('full', 'homet')]},
        {'id': 'parents', 'name': "Simone's parents", 'variants': [
            collections.OrderedDict([('id', pid), ('name', name),
                                     ('events', [] if path is None
                                      else L.care_events(path, sched, med, share))])
            for pid, (name, path, sched, med, share) in P2.PARENTS.items()
            if pid in ('none', 'br50', 'us50')]},
    ]),
    ('conditions', L.CONDITIONS),
])

with open(os.path.join(HERE, 'grid-housing.json'), 'w') as f:
    json.dump(grid, f, indent=2)
    f.write('\n')

if __name__ == '__main__':
    n = 1
    for d in grid['dimensions']:
        n *= len(d['variants'])
    print(f'{n} combinations x {len(L.CONDITIONS)} = {n * len(L.CONDITIONS)} sims')
    print(f'description {len(grid["description"])} chars\n')
    usd = lambda v: '$' + format(round(v), ',')
    print(f"{'variant':<30}{'down':>11}{'P&I/yr':>11}{'carry/yr':>11}"
          f"{'yr-1 total':>12}{'vs base':>11}")
    bl = None
    for hid, name, price, rate, term, down in HOUSING:
        d, pi, c = price * down, pmt(price * (1 - down), rate, term), carry(price)
        tot = pi + c
        if hid == 'base':
            bl = tot
        print(f'{name:<30}{usd(d):>11}{usd(pi):>11}{usd(c):>11}{usd(tot):>12}'
              f'{(usd(tot - bl) if bl else ""):>11}')
