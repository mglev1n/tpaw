#!/usr/bin/env python3
"""The household's real inputs, as of September 2026.

Supersedes the invented figures in examples/location and examples/parents,
which used a flat $500,000 gross, a $400,000 portfolio and two 37-year-olds
as placeholders.

PRIVACY. The values below are ILLUSTRATIVE PLACEHOLDERS, not the real ones.
The real account balances and salaries live in inputs.local.json, which is
gitignored, and override these on load. That keeps a fork of a public
repository free of account-level financial detail while leaving the model
structure, and every derivation built on it, reviewable in the tree. Delete
or rename the local file and everything here still runs on the placeholders.
"""
import collections, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = 2026

# --- People ---------------------------------------------------------------
AGE = {'michael': 37, 'simone': 38}
MAX_AGE = 95

# --- Balances -------------------------------------------------------------
# Grouped by TAX CHARACTER, because the New Jersey retirement-income
# exclusion and the eventual withdrawal order both depend on it. A household
# that is half qualified and half taxable does not face the same NJ bill as
# one drawing entirely from a 403(b).
ACCOUNTS = collections.OrderedDict([
    ('taxable-brokerage', [('Taxable brokerage', 150_000.0)]),
    ('tax-deferred', [('403(b) / IRA / TSP', 350_000.0)]),
    ('roth', [('Roth IRA', 60_000.0)]),
    ('hsa', [('HSA', 20_000.0)]),
    ('cash', [('Savings and checking, net of cards', 250_000.0)]),
])
SIMONE_ALLOWANCE = 50_000.0
SIMONE_SPLIT = {'cash': 0.5, 'tax-deferred': 0.5}

# Kept out of the simulated portfolio: TPAW amortizes whatever it is given,
# so a reserve left inside would be spent down like any other asset.
EMERGENCY_RESERVE = 50_000.0

# --- Income ---------------------------------------------------------------
# Michael's figure excludes investment returns, which the simulation models
# on the portfolio itself rather than as income.
MICHAEL_GROSS = 300_000
SIMONE_FELLOW_GROSS = 90_000
SIMONE_FELLOW_END = (2027, 6)      # last month at the fellowship rate
SIMONE_ATTENDING_GROSS = 250_000   # ASSUMPTION - to be swept

# --- Spending -------------------------------------------------------------
# Whether the stated monthly figure includes current housing is an open
# question; HOUSING_IN_EXPENSES toggles the reading and cashflow.py reports
# both, because the savings rate is more sensitive to this than to anything
# else on this page.
LIVING_EXPENSES_PER_MONTH = 6_000
HOUSING_IN_EXPENSES = False
CURRENT_RENT_PER_MONTH = 3_000     # ASSUMPTION, only used when the above is False

# --- Local override -------------------------------------------------------
LOCAL_PATH = os.path.join(HERE, 'inputs.local.json')
USING_LOCAL = os.path.exists(LOCAL_PATH)
if USING_LOCAL:
    _local = json.load(open(LOCAL_PATH))
    _g = globals()
    for _k, _v in _local.items():
        if _k.startswith('_') or _k not in _g:
            continue
        if _k == 'ACCOUNTS':
            _g[_k] = collections.OrderedDict(
                (_cat, [(_n, float(_amt)) for _n, _amt in _rows])
                for _cat, _rows in _v.items())
        elif _k == 'SIMONE_FELLOW_END':
            _g[_k] = tuple(_v)
        else:
            _g[_k] = _v


def totals():
    out = {k: sum(v for _n, v in rows) for k, rows in ACCOUNTS.items()}
    for k, frac in SIMONE_SPLIT.items():
        out[k] = out.get(k, 0.0) + SIMONE_ALLOWANCE * frac
    return out


def simulated_portfolio():
    return sum(totals().values()) - EMERGENCY_RESERVE


if __name__ == '__main__':
    t = totals()
    net_worth = sum(t.values())
    usd = lambda v: '$' + format(round(v), ',')
    print('=' * 66)
    print('PORTFOLIO BY TAX CHARACTER (Sep 2026)'
          + ('' if USING_LOCAL else '   [PLACEHOLDERS - no inputs.local.json]'))
    print('=' * 66)
    for k in ACCOUNTS:
        print(f'{k:<20}{usd(t[k]):>14}{t[k] / net_worth:>9.1%}')
    print(f'{"":<20}{"-" * 14:>14}')
    print(f'{"total":<20}{usd(net_worth):>14}')
    print(f'\n  less emergency reserve    {usd(-EMERGENCY_RESERVE)}')
    print(f'  -> simulated portfolio    {usd(simulated_portfolio())}')
    qual = t['tax-deferred'] + t['roth'] + t['hsa']
    print(f'\n  tax-deferred + Roth + HSA {usd(qual)}  ({qual / net_worth:.0%})')
    print(f'  taxable + cash            {usd(t["taxable-brokerage"] + t["cash"])}'
          f'  ({(t["taxable-brokerage"] + t["cash"]) / net_worth:.0%})')
