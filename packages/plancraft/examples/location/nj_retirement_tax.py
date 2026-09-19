#!/usr/bin/env python3
"""Post-hoc New Jersey retirement-income tax on the draws the grid produces.

The NJ retirement tax cannot live inside the grid as a constant. It depends on
the annual PORTFOLIO DRAW, which is set jointly by the savings rate, the
retirement age and the house -- three separate grid dimensions -- and it is a
step function with a hard cliff, so it cannot be averaged. Instead: simulate
each NJ cell, read the median draw year by year, tax it, and convert the
resulting stream into the level annuity that TPAW would have amortized it into.

Draw = withdrawalsTotal - Social Security. TPAW adds retirement income to the
portfolio as a contribution and then withdraws gross spending from the pooled
balance, so withdrawalsTotal is spending, not the draw.

Caveat: every dollar of the draw is taxed as ordinary retirement income and
every dollar claims the NJ retirement-income exclusion. A real household draws
from a mix of tax-deferred, Roth and taxable accounts; return of basis is not
taxed at all, and capital gains are taxed but are NOT exclusion-eligible. The
two errors run in opposite directions.
"""
import csv, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import nj_retirement_tax, SS, MAX_AGE, CURRENT_AGE   # noqa: E402

REAL_RETURN = 0.030          # ~1/3 stocks at 5% / bonds at 2%, net
SS_START_AGE = 70

def median_totals_by_age(path):
    out = collections.defaultdict(float)
    with open(path) as f:
        for r in csv.DictReader(f):
            if r['series'] == 'withdrawalsTotal' and r['percentile'] == '50':
                out[int(r['person1Age'])] += float(r['value'])
    return out

def level_equivalent(stream, first_age):
    """Level annuity with the same NPV over the retirement horizon."""
    npv = sum(v / (1 + REAL_RETURN) ** (a - first_age) for a, v in stream)
    ann = sum(1 / (1 + REAL_RETURN) ** (a - first_age) for a, _ in stream)
    return npv / ann if ann else 0.0

def analyze(out_dir):
    rows = []
    for slug in sorted(os.listdir(out_dir)):
        csv_path = os.path.join(out_dir, slug, 'trajectories.csv')
        if not os.path.exists(csv_path):
            continue
        _, loc_a, loc_b, sav, rage = slug.split('-')[:5]
        loc, retire = f'{loc_a}-{loc_b}', int(rage[1:])
        ss = sum(SS[retire]) * 12
        totals = median_totals_by_age(csv_path)
        stream = []
        for age in range(retire, MAX_AGE):        # drop the stub final year
            draw = totals.get(age, 0.0) - (ss if age >= SS_START_AGE else 0.0)
            stream.append((age, nj_retirement_tax(max(0.0, draw))))
        pre = [t for a, t in stream if a < SS_START_AGE]
        post = [t for a, t in stream if a >= SS_START_AGE]
        rows.append({
            'loc': loc, 'sav': sav, 'retire': retire,
            'draw_pre': (totals.get(retire, 0.0)) if retire < SS_START_AGE else 0.0,
            'draw_post': totals.get(75, 0.0) - ss,
            'tax_pre': sum(pre) / len(pre) if pre else 0.0,
            'tax_post': sum(post) / len(post) if post else 0.0,
            'level': level_equivalent(stream, retire),
        })
    return rows

if __name__ == '__main__':
    rows = analyze(sys.argv[1])
    print(f"{'location':14}{'save':6}{'retire':>7}{'draw@ret':>11}{'draw@75':>10}"
          f"{'tax pre-SS':>12}{'tax post-SS':>13}{'level/yr':>10}{'level/mo':>10}")
    for r in rows:
        print(f"{r['loc']:14}{r['sav']:6}{r['retire']:>7}{r['draw_pre']:>11,.0f}"
              f"{r['draw_post']:>10,.0f}{r['tax_pre']:>+12,.0f}{r['tax_post']:>+13,.0f}"
              f"{r['level']:>+10,.0f}{r['level']/12:>+10,.0f}")
