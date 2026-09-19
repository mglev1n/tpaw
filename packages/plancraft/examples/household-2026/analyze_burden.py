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


def max_floor(cond, income, retire, legacy, burden=0):
    """Highest floor holdable at 90% with the given extra burden."""
    prev_f, prev_s = None, None
    for f in FLOORS:
        s = ok.get((cond, burden, income, retire, legacy, f))
        if s is None:
            continue
        if s < TARGET:
            if prev_f is None:
                return None, s   # cannot even hold the lowest rung
            return prev_f + (f - prev_f) * (prev_s - TARGET) / (prev_s - s), None
        prev_f, prev_s = f, s
    return FLOORS[-1], None


ffmt = lambda t: (f'fails {100 * (1 - t[1]):.0f}%' if t[0] is None
                  else ('>' + usd(FLOORS[-1]) if t[0] >= FLOORS[-1] else usd(t[0])))

print('=' * 98)
print('FIRST: WHAT SOCIAL SECURITY AND FERS ARE ACTUALLY DOING')
print('=' * 98)
print('Highest floor holdable at 90% with NO extra obligation and no legacy.')
print('Every earlier result in this project assumed the bottom row of each block.\n')
for cid, cname in CONDS:
    print(f'{cname} returns')
    print(f"{'':<26}" + ''.join(f'{"retire " + str(a):>16}' for a in (55, 60, 65)))
    for iid, iname in INC:
        line = f'  {iname:<24}'
        for rid in ('r55', 'r60', 'r65'):
            line += f'{ffmt(max_floor(cid, iid, rid, "none")):>16}'
        print(line)
    print()
print('"fails N%" means even a $4,000/mo floor is unaffordable N% of the time.')
print('')
print('Read the top row of each block as the plan standing on its own savings.')
print('Under severe returns it does not reach 90% at ANY floor, at any retirement')
print('age. The comfort in every earlier table was substantially borrowed from two')
print('government promises, one of which has never been checked against an')
print('earnings record.')

print('\n' + '=' * 98)
print('CAPACITY FOR EXTRA OBLIGATION, 2030-2049, HOLDING $12,000/MO AT 90%')
print('=' * 98)
print('"none" means $12,000 already fails before any extra burden is added.\n')
for lid, lname in (('none', 'No legacy'), ('m5', '$5M real legacy')):
    print(f'{lname}')
    print(f"{'':<26}" + ''.join(f'{n:>16}' for _c, n in CONDS))
    for rid, age in (('r55', 55), ('r60', 60), ('r65', 65)):
        for iid, iname in INC:
            line = f'  {"r" + str(age) + ", " + iname:<24}'
            for cid, _n in CONDS:
                line += f'{fmt(capacity(cid, iid, rid, lid, 12_000)):>16}'
            print(line)
        print()

print('=' * 98)
print('CAPACITY AT A FLOOR YOU CAN ACTUALLY HOLD')
print('=' * 98)
print('The $12,000 table is mostly empty because $12,000 is out of reach without')
print('the government income. At $8,000 -- the structural floor -- there is more')
print('to say. No legacy.\n')
for cid, cname in CONDS:
    print(f'{cname} returns')
    print(f"{'':<26}" + ''.join(f'{"retire " + str(a):>16}' for a in (55, 60, 65)))
    for iid, iname in INC:
        line = f'  {iname:<24}'
        for rid in ('r55', 'r60', 'r65'):
            line += f'{fmt(capacity(cid, iid, rid, "none", 8_000)):>16}'
        print(line)
    print()

print('=' * 98)
print('KNOWN COMMITMENTS ON THE SAME SCALE')
print('=' * 98)
for label, amt in (('Brazilian care, half share', 20_000),
                   ('Private K-12 for two (13 yrs)', 70_000),
                   ('US care, half share (peak)', 158_000),
                   ('Private college for two (4 yrs)', 190_000),
                   ('US care carried entirely (peak)', 315_000)):
    print(f'  {label:<36}{usd(amt) + "/yr":>14}')
print('\nLook each one up against the capacity tables to see which retirement age')
print('and which income assumption it requires.')
