#!/usr/bin/env python3
"""Back out the actual savings rate from the balance history.

The engine takes net contributions, and the contribution is derived from
income less tax less spending -- three inputs each carrying error. The
account history is an independent check on the result: given a starting
balance, an ending balance and an elapsed period, the contribution that
reconciles them is a function only of the return earned along the way.

So sweep the return. If the derived figure from cashflow.py lands inside the
range this produces at plausible returns, the spending input is about right.
If it lands far outside, the spending input is wrong and everything
downstream of it is too.

Both series exclude credit card balances, so they are comparable.
"""
import importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('inputs', os.path.join(HERE, 'inputs.py'))
I = importlib.util.module_from_spec(spec)
spec.loader.exec_module(I)

HISTORY = getattr(I, 'HISTORY', None)
usd = lambda v: '$' + format(round(v), ',')


def implied_annual_contribution(pv, fv, years, annual_return):
    """Level monthly contribution, paid at month end, that grows pv to fv."""
    n = round(years * 12)
    if abs(annual_return) < 1e-9:
        return (fv - pv) / years
    r = (1 + annual_return) ** (1 / 12) - 1
    future_of_pv = pv * (1 + r) ** n
    annuity = ((1 + r) ** n - 1) / r
    return (fv - future_of_pv) / annuity * 12


if __name__ == '__main__':
    if not HISTORY:
        print('No HISTORY in inputs.local.json; nothing to validate against.')
        raise SystemExit(0)
    pv, fv = HISTORY['start_value'], HISTORY['end_value']
    (y0, m0), (y1, m1) = HISTORY['start_month'], HISTORY['end_month']
    months = (y1 - y0) * 12 + (m1 - m0)
    years = months / 12
    print('=' * 72)
    print('SAVINGS RATE, BACKED OUT OF THE ACCOUNT HISTORY')
    print('=' * 72)
    print(f'{usd(pv)} ({y0}-{m0:02d})  ->  {usd(fv)} ({y1}-{m1:02d})'
          f'   over {months} months')
    print(f'growth {usd(fv - pv)}  ({(fv / pv - 1):.1%})\n')
    print('Attending salary began 2024-08, so roughly the first five months of')
    print('this window are at a trainee income and the rest at the current one.')
    print('That makes the figures below an AVERAGE over a rising income, and so')
    print('an understatement of the current rate.\n')
    print(f"{'assumed nominal return':>24}{'implied saving/yr':>20}{'of which growth':>18}")
    for r in (0.00, 0.04, 0.06, 0.08, 0.10, 0.12):
        c = implied_annual_contribution(pv, fv, years, r)
        print(f'{r:>23.0%}{usd(c):>20}{usd((fv - pv) - c * years):>18}')
    print('\nThe portfolio is about a third cash, so a blended nominal return in')
    print('the 6-8% range is the reasonable middle of that table.')
