#!/usr/bin/env python3
"""Cost of supporting two Brazilian parents (early 80s): US vs staying in Brazil.

WHAT IS SOURCED vs ESTIMATED
  Sourced (Sep 2026): 2026 federal poverty level for a household of two
  ($21,150 / $84,600 at 400%); the 2026 applicable-percentage table from
  Rev. Proc. 2025-25 (2.10% floor below 133% FPL rising to 9.96% flat from
  300-400%, hard cliff above 400% now that the enhanced subsidies have
  expired); the elimination, effective plan year 2026, of the exception that
  let lawfully present immigrants below 100% FPL claim premium tax credits
  when barred from Medicaid by immigration status; the Medicare Part A
  buy-in premium of $565/month in 2026 without 40 quarters; and the national
  average benchmark silver premium of about $1,167/month at ages 64-65.
  Estimated (NOT sourced -- treat as order-of-magnitude): every Brazilian
  figure, US long-term-care rates, Medigap pricing at age 85, and the
  BRL/USD rate.

THE STRUCTURAL POINT
  Two different questions get conflated. Health INSURANCE in the US costs
  roughly $29k/yr unsubsidized and can fall to ~$1-8k/yr with premium tax
  credits, so the pension amount matters a lot -- that is the question
  asked. But long-term CARE in the US costs 5-9x what it costs in Brazil
  and Medicare does not cover custodial care at all, while Medicaid is
  blocked by the five-year bar and then by sponsor deeming under the I-864.
  So the insurance question is worth ~$28k/yr and the care-location question
  is worth ~$150-250k/yr the moment either parent needs help. They are not
  the same order of magnitude.
"""
import collections

# --- Sourced US parameters, 2026 ------------------------------------------
FPL2 = 21_150                     # 100% FPL, household of 2, 48 states
BENCHMARK_PER_PERSON_MO = 1_167   # avg benchmark silver, age 64-65
PART_A_BUYIN_MO = 565             # <30 quarters
PART_B_MO = 202
PART_D_MO = 45
MEDIGAP_G_MO_AT_85 = 400          # estimated; age-rated
MA_PREMIUM_MO = 0                 # $0-premium Medicare Advantage alternative

# Applicable percentage, Rev. Proc. 2025-25. (lower FPL%, upper FPL%, lo%, hi%)
APPLICABLE_PCT = [
    (0.00, 1.00, None, None),     # no credit at all as of plan year 2026
    (1.00, 1.33, 0.0210, 0.0210),
    (1.33, 1.50, 0.0314, 0.0419),
    (1.50, 2.00, 0.0419, 0.0660),
    (2.00, 2.50, 0.0660, 0.0844),
    (2.50, 3.00, 0.0844, 0.0996),
    (3.00, 4.00, 0.0996, 0.0996),
]
# Cost-sharing reduction: silver actuarial value and approximate out-of-pocket
# maximum per person by FPL band. CSR applies only to silver, only to 100-250%.
CSR = [(1.00, 1.50, 0.94, 3_000), (1.50, 2.00, 0.87, 3_300),
       (2.00, 2.50, 0.73, 8_500), (2.50, 99.0, 0.70, 10_600)]

# --- Estimated care costs --------------------------------------------------
BRL_USD = 5.50
# Per-person unless marked shared: one live-in caregiver serves a couple in
# the same home, but assisted living and nursing beds are bought per person.
US_CARE_MO = {'independent': 0, 'home-care': 14_000, 'assisted-one': 7_000,
              'assisted': 7_000, 'nursing': 12_500}          # USD/month
BR_CARE_MO = {'independent': 0, 'home-care': 7_000, 'assisted-one': 4_500,
              'assisted': 4_500, 'nursing': 8_000}           # BRL/month
SHARED_CARE = {'home-care', 'assisted-one'}   # one bed, or one shared caregiver
BR_HEALTH_PLAN_MO = 4_500                 # BRL/month/person, 59+ age band
BR_LIVING_SUPPORT_MO = 2_500              # BRL/month/couple, topping up pension
US_LIVING_SUPPORT_MO = 1_200              # USD/month/couple if housed with you
TRAVEL_IF_ABROAD = 9_000                  # USD/yr, 2-3 trips for two people


def applicable_pct(fpl_ratio):
    """Required contribution as a share of income; None means no credit."""
    for lo, hi, plo, phi in APPLICABLE_PCT:
        if lo <= fpl_ratio < hi:
            if plo is None:
                return None
            if hi == lo:
                return plo
            return plo + (phi - plo) * (fpl_ratio - lo) / (hi - lo)
    return None                            # above 400% FPL: the cliff


def csr_oop(fpl_ratio):
    for lo, hi, _av, oop in CSR:
        if lo <= fpl_ratio < hi:
            return oop
    return 10_600


def us_marketplace(income):
    """Annual premium the parents pay, and their out-of-pocket exposure."""
    benchmark = BENCHMARK_PER_PERSON_MO * 12 * 2
    ratio = income / FPL2
    pct = applicable_pct(ratio)
    if pct is None:
        return benchmark, 2 * 10_600, 0.0
    net = min(benchmark, pct * income)
    return net, 2 * csr_oop(ratio), benchmark - net


def us_medicare(medigap=True):
    per_person = PART_A_BUYIN_MO + PART_B_MO + PART_D_MO + (
        MEDIGAP_G_MO_AT_85 if medigap else MA_PREMIUM_MO)
    oop = 2_000 if medigap else 2 * 6_000   # MA plans carry real OOP maxima
    return per_person * 12 * 2, oop


def annual_cost(path, care, income_usd, medicare_eligible, medigap=True):
    """Total annual cost of the couple, before their own pension is applied."""
    if path == 'us':
        if medicare_eligible:
            premium, oop = us_medicare(medigap)
            subsidy = 0.0
        else:
            premium, oop, subsidy = us_marketplace(income_usd)
        heads = 0 if care == 'independent' else (1 if care in SHARED_CARE else 2)
        care_cost = US_CARE_MO[care] * 12 * heads
        living = US_LIVING_SUPPORT_MO * 12
        return {'premium': premium, 'oop': oop, 'care': care_cost,
                'living': living, 'travel': 0,
                'total': premium + oop + care_cost + living, 'subsidy': subsidy}
    plan = BR_HEALTH_PLAN_MO * 12 * 2 / BRL_USD
    heads = 0 if care == 'independent' else (1 if care in SHARED_CARE else 2)
    care_cost = BR_CARE_MO[care] * 12 * heads / BRL_USD
    living = BR_LIVING_SUPPORT_MO * 12 / BRL_USD
    return {'premium': plan, 'oop': 2_000, 'care': care_cost, 'living': living,
            'travel': TRAVEL_IF_ABROAD,
            'total': plan + 2_000 + care_cost + living + TRAVEL_IF_ABROAD,
            'subsidy': 0.0}


def usd(v):
    return '$' + format(round(v), ',')


if __name__ == '__main__':
    print('=' * 78)
    print('1. WHAT THE PENSION BUYS: US marketplace cost by their reportable income')
    print('=' * 78)
    print('Benchmark silver for two people over 64 is about '
          f'{usd(BENCHMARK_PER_PERSON_MO * 24)}/yr before any credit.\n')
    print(f"{'their income':>14}{'% FPL':>8}{'req contrib':>13}{'they pay':>11}"
          f"{'credit':>11}{'OOP max':>10}{'worst case':>12}")
    for income in (0, 12_000, 21_150, 25_000, 30_000, 40_000, 50_000, 63_450,
                   84_600, 85_600, 100_000):
        prem, oop, sub = us_marketplace(income)
        ratio = income / FPL2
        pct = applicable_pct(ratio)
        pcts = f'{pct * 100:.2f}%' if pct else 'none'
        print(f"{usd(income):>14}{ratio * 100:>7.0f}%{pcts:>13}{usd(prem):>11}"
              f"{usd(sub):>11}{usd(oop):>10}{usd(prem + oop):>12}")
    print('\nThe same thresholds in reais, to check against what they actually draw')
    print(f'(at R${BRL_USD:.2f}/USD; two INSS pensions at the ceiling are roughly')
    print('R$16,300/month, which lands near the top of the subsidised band):\n')
    print(f"{'monthly, couple':>18}{'annual USD':>13}{'% FPL':>8}{'they pay/yr':>14}")
    for brl_mo in (3_000, 5_000, 8_000, 10_000, 13_750, 16_300, 25_000, 32_500):
        inc = brl_mo * 12 / BRL_USD
        prem, _oop, _s = us_marketplace(inc)
        print(f"{'R$' + format(brl_mo, ','):>18}{usd(inc):>13}"
              f"{inc / FPL2 * 100:>7.0f}%{usd(prem):>14}")
    print('\nBelow 100% FPL there is no credit at all as of plan year 2026 -- the')
    print('exception for immigrants barred from Medicaid by status was removed.')
    print(f'Above 400% FPL ({usd(4 * FPL2)}) the cliff returns: about '
          f'{usd(BENCHMARK_PER_PERSON_MO * 24)}/yr of credit')
    print('disappears for one extra dollar of income.')

    print('\n' + '=' * 78)
    print('2. US vs BRAZIL, by how much care they need (annual, both parents)')
    print('=' * 78)
    INC = 30_000
    print(f'Assuming reportable pension of {usd(INC)} '
          f'({INC / FPL2 * 100:.0f}% FPL), pre-Medicare.\n')
    print(f"{'care level':>14}{'US total':>12}{'Brazil total':>14}{'US - Brazil':>13}"
          f"{'ratio':>8}")
    for care in ('independent', 'home-care', 'assisted', 'nursing'):
        u = annual_cost('us', care, INC, False)['total']
        b = annual_cost('br', care, INC, False)['total']
        print(f"{care:>14}{usd(u):>12}{usd(b):>14}{usd(u - b):>13}"
              f"{u / b:>7.1f}x")
    print('\nThe insurance question moves the independent row. The care question')
    print('moves every other row, by an order of magnitude more.')

    print('\n' + '=' * 78)
    print('3. WHO PAYS: the household share under different sibling splits')
    print('=' * 78)
    print('Net of their own pension, which is assumed spent on their own costs.\n')
    print(f"{'scenario':>34}{'net/yr':>11}{'you 0%':>9}{'you 33%':>9}"
          f"{'you 50%':>9}{'you 100%':>10}")
    for label, path, care, med in (
            ('US, independent, pre-Medicare', 'us', 'independent', False),
            ('US, independent, on Medicare', 'us', 'independent', True),
            ('US, one needs assisted living', 'us', 'assisted', True),
            ('US, both need nursing care', 'us', 'nursing', True),
            ('Brazil, independent', 'br', 'independent', False),
            ('Brazil, full home care', 'br', 'home-care', False),
            ('Brazil, both in nursing care', 'br', 'nursing', False)):
        c = annual_cost(path, care, INC, med)
        net = max(0.0, c['total'] - INC)
        if care == 'assisted':          # only one parent needs it
            net = max(0.0, c['total'] - c['care'] / 2 - INC)
        print(f"{label:>34}{usd(net):>11}{usd(0):>9}{usd(net / 3):>9}"
              f"{usd(net / 2):>9}{usd(net):>10}")
