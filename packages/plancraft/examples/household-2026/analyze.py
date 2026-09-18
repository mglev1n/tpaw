#!/usr/bin/env python3
"""Tables for the household-2026 grids. Usage: analyze.py <grid.csv> <fers.csv>"""
import csv, sys

load = lambda p: [dict(r, spend=float(r['medianRetirementSpendingPerMonth']),
                       success=float(r['successProbability']))
                  for r in csv.DictReader(open(p))]
usd = lambda v: '$' + format(round(v), ',')
cell = lambda r: f"{usd(r['spend'])} {100 * r['success']:.0f}%"

HOUSE = {'ch-655k': 'Cherry Hill $655k', 'ch-850k': 'Cherry Hill $850k',
         'ch-1m': 'Cherry Hill $1.0M'}
SCHOOL = {'none': 'No children', 'public': '2 kids, public',
          'private': '2 kids, private K-12'}
PARENTS = {'none': 'No support', 'brazil': 'Brazil care', 'us': 'US care'}

rows = load(sys.argv[1])
g = lambda h, s, p: next(r for r in rows if r['condition'] == 'base-returns'
                         and r['house'] == h and r['school'] == s and r['parents'] == p)

print('=' * 92)
print('RETIREMENT SPENDING AT 60  (median $/mo, and success probability)')
print('=' * 92)
for pid, pname in PARENTS.items():
    print(f'\n{pname}')
    print(f"{'':<24}" + ''.join(f'{HOUSE[h]:>22}' for h in HOUSE))
    for sid, sname in SCHOOL.items():
        print(f'{sname:<24}' + ''.join(f'{cell(g(h, sid, pid)):>22}' for h in HOUSE))

print('\n' + '=' * 92)
print('WHAT EACH DECISION COSTS  (vs the cheapest option in its row)')
print('=' * 92)
b = g('ch-655k', 'none', 'none')['spend']
print(f'Reference: $655k house, no children, no parental support = {usd(b)}/mo\n')
for label, r in (
        ('$850k instead of $655k', g('ch-850k', 'none', 'none')),
        ('$1.0M instead of $655k', g('ch-1m', 'none', 'none')),
        ('two children, public school', g('ch-655k', 'public', 'none')),
        ('two children, private K-12', g('ch-655k', 'private', 'none')),
        ('private instead of public', g('ch-655k', 'private', 'none'))):
    ref = b if 'instead of public' not in label else g('ch-655k', 'public', 'none')['spend']
    print(f'{label:<34}{usd(r["spend"] - ref) + "/mo":>14}')
for label, r in (("parents' care in Brazil", g('ch-655k', 'public', 'brazil')),
                 ("parents' care in the US", g('ch-655k', 'public', 'us'))):
    print(f'{label:<34}'
          f'{usd(r["spend"] - g("ch-655k", "public", "none")["spend"]) + "/mo":>14}')

print('\n' + '=' * 92)
print('THE WORST CASE THAT IS STILL REALISTIC')
print('=' * 92)
w = g('ch-1m', 'private', 'us')
print(f'$1.0M house + two children in private school + US parental care:')
print(f'  {usd(w["spend"])}/mo at {100 * w["success"]:.0f}% success '
      f'(against {usd(b)}/mo for the reference)')

fers = load(sys.argv[2])
f = lambda fe, r, l: next(x for x in fers if x['condition'] == 'base-returns'
                          and x['fers'] == fe and x['retire'] == r
                          and x['lifestyle'] == l)
print('\n' + '=' * 92)
print('DOES FERS CHANGE ANYTHING?  ($850k house, 2 kids public, no parental support)')
print('=' * 92)
print(f"{'':<14}" + ''.join(f'{"retire " + a[1:]:>30}' for a in ('r55', 'r60', 'r65')))
for lid, lname in (('lean', '$8,000/mo'), ('mid', '$10,000/mo'), ('rich', '$12,000/mo')):
    line = f'{lname:<14}'
    for a in ('r55', 'r60', 'r65'):
        wo, wi = f('without', a, lid), f('with', a, lid)
        line += f'{cell(wo) + " -> " + cell(wi):>30}'
    print(line)
print('\nEach cell is Social Security only -> with the FERS annuity.')
print(f"{'FERS adds':<14}" + ''.join(
    f'{usd(f("with", a, "lean")["spend"] - f("without", a, "lean")["spend"]) + "/mo":>30}'
    for a in ('r55', 'r60', 'r65')))
