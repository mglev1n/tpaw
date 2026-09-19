#!/usr/bin/env python3
"""Capacity: how much more can be taken on. Usage: analyze_burden.py <csv>"""
import collections, csv, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(n, p):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


BU = _load('burden', os.path.join(HERE, 'burden.py'))
FLOORS, BURDENS, TARGET = BU.P2.FLOORS, BU.BURDENS, 0.90
usd = lambda v: '$' + format(round(v), ',')

rows = list(csv.DictReader(open(sys.argv[1])))
ok = {}
for r in rows:
    ok[(r['condition'], int(r['burden'][1:]) * 1000, r['income'], r['retire'],
        r['legacy'], int(r['floor'][1:]) * 1000)] = float(r['successProbability'])


def capacity(cond, income, retire, legacy, floor):
    """Largest burden still holding `floor` at 90%, interpolated."""
    prev_b, prev_s = None, None
    for b in BURDENS:
        s = ok.get((cond, b, income, retire, legacy, floor))
        if s is None:
            continue
        if s < TARGET:
            if prev_b is None:
                return None
            return prev_b + (b - prev_b) * (prev_s - TARGET) / (prev_s - s)
        prev_b, prev_s = b, s
    return BURDENS[-1]


INC = [('neither', 'Own savings only'), ('ss', 'Social Security only'),
       ('both', 'Soc Sec + FERS')]
CONDS = [('base-returns', 'Base'), ('pessimistic', 'Pessimistic'),
         ('severe', 'Severe')]
fmt = lambda v: ('none' if v is None else
                 ('>' + usd(BURDENS[-1]) if v >= BURDENS[-1] else usd(v)))

print('=' * 98)
print('EXTRA OBLIGATION ABSORBABLE, 2030-2049, HOLDING A $12,000/MO FLOOR AT 90%')
print('=' * 98)
print('"none" means the floor already fails with no extra burden at all.\n')
for lid, lname in (('none', 'No legacy'), ('m5', '$5M real legacy')):
    print(f'{lname}')
    print(f"{'':<22}" + ''.join(f'{n:>18}' for _c, n in CONDS))
    for rid, age in (('r55', 55), ('r60', 60), ('r65', 65)):
        for iid, iname in INC:
            line = f'  {"retire " + str(age) + ", " + iname:<20}'
            for cid, _n in CONDS:
                line += f'{fmt(capacity(cid, iid, rid, lid, 12_000)):>18}'
            print(line)
        print()

print('=' * 98)
print('WHAT SOCIAL SECURITY AND FERS ARE WORTH IN CAPACITY')
print('=' * 98)
print('Every earlier result in this project assumed both. This is the difference,')
print('at a $12,000 floor and no legacy:\n')
print(f"{'':<16}" + ''.join(f'{n:>20}' for _c, n in CONDS))
for rid, age in (('r55', 55), ('r60', 60), ('r65', 65)):
    line = f'  retire {age:<8}'
    for cid, _n in CONDS:
        a = capacity(cid, 'neither', rid, 'none', 12_000)
        b = capacity(cid, 'both', rid, 'none', 12_000)
        line += (f'{(usd(b - a) + "/yr" if a is not None and b is not None else "n/a"):>20}')
    print(line)

print('\n' + '=' * 98)
print('CAPACITY BY FLOOR  (own savings only, no legacy, severe returns)')
print('=' * 98)
print('Lowering the floor you promise buys capacity for obligations.\n')
print(f"{'floor':<14}" + ''.join(f'{"retire " + str(a):>16}' for a in (55, 60, 65)))
for f in FLOORS:
    line = f'{usd(f) + "/mo":<14}'
    for rid in ('r55', 'r60', 'r65'):
        line += f"{fmt(capacity('severe', 'neither', rid, 'none', f)):>16}"
    print(line)

print('\n' + '=' * 98)
print('KNOWN COMMITMENTS ON THE SAME SCALE')
print('=' * 98)
for label, amt in (('Brazilian care, half share', 20_000),
                   ('Private K-12 for two (13 yrs)', 70_000),
                   ('US care, half share (peak)', 158_000),
                   ('Private college for two (4 yrs)', 190_000),
                   ('US care carried entirely (peak)', 315_000)):
    print(f'  {label:<36}{usd(amt) + "/yr":>14}')
print('\nCompare each against the capacity tables above to see which retirement')
print('age and income assumption it requires.')
