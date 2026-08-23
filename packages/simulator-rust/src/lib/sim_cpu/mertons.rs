// CPU port of
// packages/simulator-cuda/src/simulate/cuda_process_run_x_mfn_simulated_x_mfn/mertons_formula.h
// in f64 ("replication mode" numerics).

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MertonsFormulaResult {
    pub stock_allocation: f64,
    pub spending_tilt: f64, // monthly
}

#[derive(Clone, Copy, Debug)]
pub struct PlainMertonsFormulaClosure {
    pub annual_equity_premium_by_variance: f64,
    pub c0: f64,
    pub c1: f64,
    pub annual_additional_spending_tilt: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct EffectiveMertonsFormulaClosure {
    pub plain_closure: PlainMertonsFormulaClosure,
    pub rra_for_all_stocks: f64,
}

pub fn annual_to_monthly_rate(annual: f64) -> f64 {
    (1.0 + annual).powf(1.0 / 12.0) - 1.0
}

pub fn monthly_to_annual_rate(monthly: f64) -> f64 {
    (1.0 + monthly).powi(12) - 1.0
}

pub fn saturate(x: f64) -> f64 {
    // CUDA __saturatef: clamps to [0, 1], NaN -> 0.
    if x.is_nan() {
        0.0
    } else {
        x.clamp(0.0, 1.0)
    }
}

pub fn get_plain_mertons_formula_closure(
    annual_r: f64, // bond rate
    annual_equity_premium: f64,
    annual_variance_stocks: f64,
    time_preference: f64,
    annual_additional_spending_tilt: f64,
) -> PlainMertonsFormulaClosure {
    let rho = time_preference;
    let annual_equity_premium_by_variance_stocks = annual_equity_premium / annual_variance_stocks;
    let annual_equity_premium_pow2_by_2variance_stocks =
        annual_equity_premium * annual_equity_premium_by_variance_stocks * 0.5;
    PlainMertonsFormulaClosure {
        annual_equity_premium_by_variance: annual_equity_premium_by_variance_stocks,
        c0: annual_r - rho + annual_equity_premium_pow2_by_2variance_stocks,
        c1: annual_equity_premium_pow2_by_2variance_stocks,
        annual_additional_spending_tilt,
    }
}

pub fn plain_mertons_formula(
    closure: &PlainMertonsFormulaClosure,
    rra_including_pos_infinity: f64,
) -> MertonsFormulaResult {
    if rra_including_pos_infinity == f64::INFINITY {
        return MertonsFormulaResult {
            stock_allocation: 0.0,
            spending_tilt: annual_to_monthly_rate(closure.annual_additional_spending_tilt),
        };
    }
    let gamma = rra_including_pos_infinity;
    let one_over_gamma = 1.0 / gamma;
    let one_over_gamma_pow2 = one_over_gamma * one_over_gamma;
    let stock_allocation = closure.annual_equity_premium_by_variance * one_over_gamma;
    let annual_spending_tilt = one_over_gamma * closure.c0
        + (one_over_gamma_pow2 * closure.c1 + closure.annual_additional_spending_tilt);
    MertonsFormulaResult {
        stock_allocation,
        spending_tilt: annual_to_monthly_rate(annual_spending_tilt),
    }
}

pub fn get_rra_for_all_stocks(annual_equity_premium: f64, annual_sigma_pow2: f64) -> f64 {
    annual_equity_premium / annual_sigma_pow2
}

pub fn get_effective_mertons_formula_closure(
    annual_r: f64, // bond rate
    annual_equity_premium: f64,
    annual_variance_stocks: f64,
    time_preference: f64,
    annual_additional_spending_tilt: f64,
) -> EffectiveMertonsFormulaClosure {
    // A negative equity premium would mean leverage; ignore stocks instead by
    // clamping the premium to 0 (see mertons_formula.h).
    let annual_effective_equity_premium = annual_equity_premium.max(0.0);
    EffectiveMertonsFormulaClosure {
        plain_closure: get_plain_mertons_formula_closure(
            annual_r,
            annual_effective_equity_premium,
            annual_variance_stocks,
            time_preference,
            annual_additional_spending_tilt,
        ),
        rra_for_all_stocks: get_rra_for_all_stocks(
            annual_effective_equity_premium,
            annual_variance_stocks,
        ),
    }
}

pub fn effective_mertons_formula(
    closure: &EffectiveMertonsFormulaClosure,
    rra_including_pos_infinity: f64,
) -> MertonsFormulaResult {
    // Clamp rra to 100% stocks.
    let effective_rra = closure.rra_for_all_stocks.max(rra_including_pos_infinity);
    let mut result = plain_mertons_formula(&closure.plain_closure, effective_rra);
    result.stock_allocation = saturate(result.stock_allocation);
    result
}

pub fn effective_mertons_formula_stock_allocation_only(
    annual_equity_premium: f64,
    annual_variance_stocks: f64,
    rra_including_pos_infinity: f64,
) -> f64 {
    let closure = get_effective_mertons_formula_closure(
        0.0, // not used
        annual_equity_premium,
        annual_variance_stocks,
        0.0, // not used
        0.0, // not used
    );
    effective_mertons_formula(&closure, rra_including_pos_infinity).stock_allocation
}

#[cfg(test)]
mod tests {
    use super::*;

    fn approx(a: f64, b: f64) {
        let eps = 1e-9 * b.abs().max(1.0);
        assert!((a - b).abs() < eps, "{} != {}", a, b);
    }

    // Ports of the doctest truth values in mertons_formula.cu.
    fn do_plain_test(
        annual_stock_returns: f64,
        annual_bond_returns: f64,
        annual_variance_stocks: f64,
        rra: f64,
        time_preference: f64,
        annual_additional_spending_tilt: f64,
        truth_stock_allocation: f64,
        truth_spending_tilt: f64,
    ) {
        let closure = get_plain_mertons_formula_closure(
            annual_bond_returns,
            annual_stock_returns - annual_bond_returns,
            annual_variance_stocks,
            time_preference,
            annual_additional_spending_tilt,
        );
        let result = plain_mertons_formula(&closure, rra);
        approx(result.stock_allocation, truth_stock_allocation);
        approx(result.spending_tilt, truth_spending_tilt);
    }

    #[test]
    fn plain_mertons_formula_truths() {
        do_plain_test(0.05, 0.03, 0.01, 4.0, 0.01, 0.0, 0.5000000000000001, 0.0009327004773649339);
        do_plain_test(0.05, 0.03, 0.01, 0.04, 0.01, 0.0, 50.00000000000001, 0.24962776727305425);
        do_plain_test(0.05, 0.03, 0.01, f64::INFINITY, 0.01, 0.0, 0.0, 0.0);
        do_plain_test(0.03, 0.03, 0.01, 4.0, 0.01, 0.0, 0.0, 0.00041571484472902043);
        do_plain_test(0.05, 0.03, 0.01, 4.0, -0.1, 0.0, 0.5000000000000001, 0.003173196227570285);
        do_plain_test(0.05, 0.03, 0.01, 4.0, 0.01, 1.0, 0.5000000000000001, 0.059958441910258564);
        do_plain_test(
            0.05,
            0.03,
            0.01,
            2.0000000000000004,
            0.01,
            0.0,
            1.0,
            0.002059836269842741,
        );
    }

    #[test]
    fn rra_for_all_stocks_truths() {
        approx(get_rra_for_all_stocks(0.05 - 0.03, 0.01), 2.0000000000000004);
        approx(get_rra_for_all_stocks(0.0, 0.01), 0.0);
    }

    fn do_effective_test(
        annual_stock_returns: f64,
        annual_bond_returns: f64,
        sigma_pow2: f64,
        rra: f64,
        time_preference: f64,
        annual_additional_spending_tilt: f64,
        truth_stock_allocation: f64,
        truth_spending_tilt: f64,
    ) {
        let closure = get_effective_mertons_formula_closure(
            annual_bond_returns,
            annual_stock_returns - annual_bond_returns,
            sigma_pow2,
            time_preference,
            annual_additional_spending_tilt,
        );
        let result = effective_mertons_formula(&closure, rra);
        approx(result.stock_allocation, truth_stock_allocation);
        approx(result.spending_tilt, truth_spending_tilt);
    }

    #[test]
    fn effective_mertons_formula_truths() {
        do_effective_test(0.05, 0.03, 0.01, 4.0, 0.01, 0.0, 0.5000000000000001, 0.0009327004773649339);
        do_effective_test(
            0.05,
            0.03,
            0.01,
            2.0000000000000004,
            0.01,
            0.0,
            1.0,
            0.002059836269842741,
        );
        do_effective_test(0.05, 0.03, 0.01, 0.05, 0.01, 0.0, 1.0, 0.002059836269842741);
        do_effective_test(0.02, 0.03, 0.01, 4.0, 0.01, 0.0, 0.0, 0.00041571484472902043);
    }
}
