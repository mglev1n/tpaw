#!/usr/bin/env python3
"""Derive net income and the implied savings rate from the stated inputs.

The engine models one portfolio and takes NET CONTRIBUTIONS, so savings is
not an input -- it is income less tax less spending. That makes the savings
rate a derived quantity worth checking against what actually gets saved: if
these two disagree, something in the inputs is wrong.

Residence is Cherry Hill, NJ (the target), with both spouses working in
Philadelphia. New Jersey credits the Philadelphia non-resident wage tax in
full against NJ income tax; the rates and their sources are in
examples/location/build.py.
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


I = _load('inputs', os.path.join(HERE, 'inputs.py'))
loc = _load('loc', os.path.join(os.path.dirname(HERE), 'location', 'build.py'))

PRETAX_DEFERRAL = 70_000   # ASSUMPTION: 403(b)/457/TSP employee + employer
usd = lambda v: '$' + format(round(v), ',')


def net_income(gross, state='nj', pretax=PRETAX_DEFERRAL):
    """After federal, payroll, Philadelphia wage and state tax."""
    taxed = max(0.0, gross - pretax)
    fed, _p = loc.federal_and_payroll(taxed)
    # Payroll tax applies to gross, not to income net of deferrals.
    e1, e2, WB = gross * 0.77, gross * 0.23, 184_000
    payroll = ((min(e1, WB) + min(e2, WB)) * 0.062 + gross * 0.0145
               + max(0.0, gross - 250_000) * 0.009)
    philly = gross * loc.PHILLY_NONRESIDENT
    if state == 'pa':
        state_tax = taxed * loc.PA_STATE
    else:
        state_tax = max(0.0, loc.nj_tax(taxed - 2_000) - philly)
    return gross - fed - payroll - philly - state_tax


_fy, _fm = I.SIMONE_FELLOW_END
PHASES = [
    (f'now - {_fy}-{_fm:02d}  (Simone fellow)',
     I.MICHAEL_GROSS + I.SIMONE_FELLOW_GROSS),
    (f'{_fy}-{_fm + 1:02d} onward  (Simone attending)',
     I.MICHAEL_GROSS + I.SIMONE_ATTENDING_GROSS),
]

if __name__ == '__main__':
    living = I.LIVING_EXPENSES_PER_MONTH * 12
    housing_now = 0 if I.HOUSING_IN_EXPENSES else I.CURRENT_RENT_PER_MONTH * 12
    print('=' * 78)
    print('DERIVED NET INCOME AND SAVINGS  (Cherry Hill NJ, both working in Philadelphia)')
    print('=' * 78)
    print(f'Assumes {usd(PRETAX_DEFERRAL)}/yr of pre-tax deferrals across 403(b)/457/TSP,')
    print(f'and that the stated {usd(living)}/yr of living expenses '
          f'{"includes" if I.HOUSING_IN_EXPENSES else "EXCLUDES"} housing.\n')
    print(f"{'phase':<38}{'gross':>11}{'net':>11}{'spend':>11}{'saved':>11}{'rate':>7}")
    for label, gross in PHASES:
        net = net_income(gross)
        spend = living + housing_now
        saved = net - spend
        print(f'{label:<38}{usd(gross):>11}{usd(net):>11}{usd(spend):>11}'
              f'{usd(saved):>11}{saved / net:>6.0%}')
    print(f'\n  "saved" is the net portfolio contribution the simulation would use,')
    print(f'  INCLUDING the {usd(PRETAX_DEFERRAL)} of pre-tax deferrals (they are savings,')
    print(f'  not spending). validate_savings.py checks it against the accounts.')
    obs = getattr(I, 'OBSERVED_SPEND_LAST_12MO', None)
    if obs:
        print(f'\n  Observed outgoings over the trailing twelve months were {usd(obs)},')
        print(f'  one-offs included, against the {usd(living)}/yr modelled here.')
        print(f'  Modelling above the recurring run-rate is deliberate: one-offs')
        print(f'  recur in kind even when no single one repeats.')

    print('\n' + '-' * 78)
    print('SENSITIVITY: the two inputs the savings rate is most exposed to')
    print('-' * 78)
    print(f"{'reading of the stated monthly spend':<42}{'saved 2026':>13}{'saved 2028+':>14}")
    for label, inc_housing, rent in (
            ('excludes housing, rent $3,000/mo', False, 3_000),
            ('excludes housing, rent $4,000/mo', False, 4_000),
            ('includes housing (all-in burn)', True, 0)):
        h = 0 if inc_housing else rent * 12
        a = net_income(PHASES[0][1]) - living - h
        b = net_income(PHASES[1][1]) - living - h
        print(f'{label:<42}{usd(a):>13}{usd(b):>14}')
    print(f"\n{'Simone attending salary':<42}{'net':>13}{'saved':>14}")
    for s in (200_000, 250_000, 300_000):
        g = I.MICHAEL_GROSS + s
        n = net_income(g)
        print(f'{usd(s):<42}{usd(n):>13}{usd(n - living - housing_now):>14}')
