// CPU port of the TPAW strategy:
// - packages/simulator-cuda/src/simulate/cuda_process_run_x_mfn_simulated_x_mfn/cuda_process_tpaw_run_x_mfn_simulated_x_mfn.cu
//   (the per-(run, month) precomputed Entry, computed here on the fly), and
// - packages/simulator-cuda/src/simulate/run/run_tpaw.cu (the two-pass
//   expected/normal simulation).

use crate::cuda_bridge::OptCURRENCY;

use super::mertons::{
    effective_mertons_formula, effective_mertons_formula_stock_allocation_only,
    get_effective_mertons_formula_closure, saturate as float_saturate, MertonsFormulaResult,
};
use super::run_common::{
    apply_allocation, apply_contributions_and_withdrawals, apply_withdrawal_ceiling_and_floor,
    AccountForWithdrawal, MonthlyAndAnnual, RunOutput, StocksAndBondsF64, TargetWithdrawals,
};

pub struct TpawParams<'a> {
    pub num_months: usize,
    pub num_months_to_simulate: usize,
    pub current_portfolio_balance: f64,
    pub withdrawal_start_month: u32,
    pub spending_ceiling: OptCURRENCY,
    pub spending_floor: OptCURRENCY,
    pub income_by_mfn: &'a [f64],
    pub essential_expense_by_mfn: &'a [f64],
    pub discretionary_expense_by_mfn: &'a [f64],
    pub rra_unique: &'a [f64],
    pub rra_index_by_mfn: &'a [u32],
    pub annual_empirical_log_variance_stocks: f64,
    pub time_preference: f64,
    pub annual_additional_spending_tilt: f64,
    pub legacy_rra_including_pos_infinity: f64,
    pub legacy: f64,
}

// Cuda_Processed_TPAW_Run_x_MFNSimulated_x_MFN::Entry.
#[derive(Clone, Copy, Debug)]
pub struct TpawEntry {
    pub npv_income_without_current_month: f64,
    pub npv_essential_expenses_without_current_month: f64,
    pub npv_discretionary_expenses_without_current_month: f64,
    pub npv_legacy_exact: f64,
    pub stock_allocation_total_portfolio: f64,
    pub legacy_stock_allocation: f64,
    pub spending_tilt: f64,
    pub cumulative_1_plus_g_over_1_plus_r: f64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TpawExpectedRunData {
    pub wealth_starting: f64,
    pub elasticity_of_extra_withdrawal_goals_wrt_wealth: f64,
    pub elasticity_of_legacy_goals_wrt_wealth: f64,
}

pub fn tpaw_entry(
    p: &TpawParams,
    month_index: usize,
    expected_returns: &MonthlyAndAnnual,
) -> TpawEntry {
    let monthly_equity_premium =
        expected_returns.monthly.stocks - expected_returns.monthly.bonds;
    let annual_equity_premium = expected_returns.annual.stocks - expected_returns.annual.bonds;
    let one_over_1p_bonds = 1.0 / (1.0 + expected_returns.monthly.bonds);

    let closure = get_effective_mertons_formula_closure(
        expected_returns.annual.bonds,
        annual_equity_premium,
        p.annual_empirical_log_variance_stocks,
        p.time_preference,
        p.annual_additional_spending_tilt,
    );
    let merton_by_unique: Vec<MertonsFormulaResult> = p
        .rra_unique
        .iter()
        .map(|&rra| effective_mertons_formula(&closure, rra))
        .collect();

    let mut npv_income_with = 0.0f64;
    let mut npv_essential_expense_with = 0.0f64;
    let mut npv_discretionary_expense_with = 0.0f64;
    let mut cumulative_1_plus_g_over_1_plus_r = 0.0f64;

    for ii in (month_index..p.num_months).rev() {
        let merton_result = &merton_by_unique[p.rra_index_by_mfn[ii] as usize];
        let one_plus_r_portfolio = 1.0
            + (monthly_equity_premium * merton_result.stock_allocation
                + expected_returns.monthly.bonds);
        let one_over_one_plus_r_portfolio = 1.0 / one_plus_r_portfolio;

        npv_income_with = npv_income_with * one_over_1p_bonds + p.income_by_mfn[ii];
        npv_essential_expense_with =
            npv_essential_expense_with * one_over_1p_bonds + p.essential_expense_by_mfn[ii];
        npv_discretionary_expense_with = npv_discretionary_expense_with
            * one_over_one_plus_r_portfolio
            + p.discretionary_expense_by_mfn[ii];

        let one_plus_g_over_1_plus_r =
            (merton_result.spending_tilt + 1.0) * one_over_one_plus_r_portfolio;
        cumulative_1_plus_g_over_1_plus_r =
            cumulative_1_plus_g_over_1_plus_r * one_plus_g_over_1_plus_r + 1.0;
    }

    let merton_result = &merton_by_unique[p.rra_index_by_mfn[month_index] as usize];

    let legacy_stock_allocation = effective_mertons_formula_stock_allocation_only(
        annual_equity_premium,
        p.annual_empirical_log_variance_stocks,
        p.legacy_rra_including_pos_infinity,
    );
    let r_of_legacy_portfolio =
        monthly_equity_premium * legacy_stock_allocation + expected_returns.monthly.bonds;
    let num_months_left = p.num_months - month_index - 1;
    let legacy_npv_denominator =
        (1.0 + r_of_legacy_portfolio).powi(num_months_left as i32 + 1);
    let legacy_npv = p.legacy / legacy_npv_denominator;

    TpawEntry {
        npv_income_without_current_month: npv_income_with - p.income_by_mfn[month_index],
        npv_essential_expenses_without_current_month: npv_essential_expense_with
            - p.essential_expense_by_mfn[month_index],
        npv_discretionary_expenses_without_current_month: npv_discretionary_expense_with
            - p.discretionary_expense_by_mfn[month_index],
        npv_legacy_exact: legacy_npv,
        stock_allocation_total_portfolio: merton_result.stock_allocation,
        legacy_stock_allocation,
        spending_tilt: merton_result.spending_tilt,
        cumulative_1_plus_g_over_1_plus_r,
    }
}

// The stock allocation reported for the expected run at month 0, for every mfn
// (kernel writes stock_allocation_total_portfolio_expected_run_by_mfn).
pub fn tpaw_stock_allocation_total_portfolio_for_month_0_by_mfn(
    p: &TpawParams,
    expected_returns_at_month_0: &MonthlyAndAnnual,
) -> Vec<f64> {
    let annual_equity_premium =
        expected_returns_at_month_0.annual.stocks - expected_returns_at_month_0.annual.bonds;
    let closure = get_effective_mertons_formula_closure(
        expected_returns_at_month_0.annual.bonds,
        annual_equity_premium,
        p.annual_empirical_log_variance_stocks,
        p.time_preference,
        p.annual_additional_spending_tilt,
    );
    let merton_by_unique: Vec<f64> = p
        .rra_unique
        .iter()
        .map(|&rra| effective_mertons_formula(&closure, rra).stock_allocation)
        .collect();
    p.rra_index_by_mfn
        .iter()
        .map(|&i| merton_by_unique[i as usize])
        .collect()
}

struct PrecomputationAtStart {
    wealth: f64,
    expenses_scale_discretionary: f64,
    expenses_scale_legacy: f64,
    npv_scaled_discretionary: f64,
    npv_scaled_legacy: f64,
    npv_scaled_general: f64,
}

fn get_precomputation_at_start(
    balance_starting: f64,
    entry: &TpawEntry,
    current_month_income: f64,
    current_month_essential_expense: f64,
    current_month_discretionary_expense: f64,
    expected_run_data_if_normal_run: Option<&TpawExpectedRunData>,
) -> PrecomputationAtStart {
    let wealth =
        balance_starting + entry.npv_income_without_current_month + current_month_income;

    let (expenses_scale_discretionary, expenses_scale_legacy) =
        match expected_run_data_if_normal_run {
            None => (1.0, 1.0),
            Some(expected) => {
                let percentage_increase_in_wealth_over_scheduled =
                    if expected.wealth_starting == 0.0 {
                        0.0
                    } else {
                        wealth / expected.wealth_starting - 1.0
                    };
                (
                    (percentage_increase_in_wealth_over_scheduled
                        * expected.elasticity_of_extra_withdrawal_goals_wrt_wealth
                        + 1.0)
                        .max(0.0),
                    (percentage_increase_in_wealth_over_scheduled
                        * expected.elasticity_of_legacy_goals_wrt_wealth
                        + 1.0)
                        .max(0.0),
                )
            }
        };

    let mut account = AccountForWithdrawal::new(wealth);
    account.withdraw(
        entry.npv_essential_expenses_without_current_month + current_month_essential_expense,
    );
    let npv_scaled_discretionary = account.withdraw(
        (entry.npv_discretionary_expenses_without_current_month
            + current_month_discretionary_expense)
            * expenses_scale_discretionary,
    );
    let npv_scaled_legacy = account.withdraw(entry.npv_legacy_exact * expenses_scale_legacy);
    let npv_scaled_general = account.balance;

    PrecomputationAtStart {
        wealth,
        expenses_scale_discretionary,
        expenses_scale_legacy,
        npv_scaled_discretionary,
        npv_scaled_legacy,
        npv_scaled_general,
    }
}

fn get_expected_run_data(
    stock_allocation: f64,
    legacy_stock_allocation: f64,
    wealth_at_start: f64,
    precomputation: &PrecomputationAtStart,
) -> TpawExpectedRunData {
    // Effectively the percentage of wealth that is in stocks.
    let elasticity_of_wealth_wrt_stocks = if wealth_at_start == 0.0 {
        (legacy_stock_allocation + stock_allocation + stock_allocation) / 3.0
    } else {
        let legacy_in_stocks = precomputation.npv_scaled_legacy * legacy_stock_allocation;
        let discretionary_and_legacy_in_stocks =
            precomputation.npv_scaled_discretionary * stock_allocation + legacy_in_stocks;
        let all_in_stocks = precomputation.npv_scaled_general * stock_allocation
            + discretionary_and_legacy_in_stocks;
        all_in_stocks / wealth_at_start
    };

    let elasticity_of_extra_withdrawal_goals_wrt_wealth =
        if elasticity_of_wealth_wrt_stocks == 0.0 {
            0.0
        } else {
            stock_allocation / elasticity_of_wealth_wrt_stocks
        };
    let elasticity_of_legacy_goals_wrt_wealth = if elasticity_of_wealth_wrt_stocks == 0.0 {
        0.0
    } else {
        legacy_stock_allocation / elasticity_of_wealth_wrt_stocks
    };

    TpawExpectedRunData {
        wealth_starting: wealth_at_start,
        elasticity_of_extra_withdrawal_goals_wrt_wealth,
        elasticity_of_legacy_goals_wrt_wealth,
    }
}

fn get_target_withdrawals_assuming_no_ceiling_or_floor(
    withdrawal_started: bool,
    curr_month_essential_expense: f64,
    curr_month_discretionary_expense: f64,
    curr_month_cumulative_1_plus_g_over_1_plus_r: f64,
    expenses_scale_discretionary: f64,
    npv_scaled_general: f64,
) -> TargetWithdrawals {
    TargetWithdrawals {
        essential: curr_month_essential_expense,
        discretionary: curr_month_discretionary_expense * expenses_scale_discretionary,
        general: if !withdrawal_started {
            0.0
        } else {
            npv_scaled_general / curr_month_cumulative_1_plus_g_over_1_plus_r
        },
    }
}

fn get_stock_allocation(
    entry: &TpawEntry,
    expenses_scale_discretionary: f64,
    expenses_scale_legacy: f64,
    balance_after_contributions_and_withdrawals: f64,
) -> f64 {
    // If savings portfolio balance is 0, approximate the limit as it goes to 0.
    let savings_portfolio_balance = balance_after_contributions_and_withdrawals.max(0.00001);
    let mut account = AccountForWithdrawal::new(
        savings_portfolio_balance + entry.npv_income_without_current_month,
    );
    account.withdraw(entry.npv_essential_expenses_without_current_month);
    let npv_discretionary = account.withdraw(
        entry.npv_discretionary_expenses_without_current_month * expenses_scale_discretionary,
    );
    let npv_legacy = account.withdraw(entry.npv_legacy_exact * expenses_scale_legacy);
    let npv_general = account.balance;

    let stocks_target = npv_legacy * entry.legacy_stock_allocation
        + npv_discretionary * entry.stock_allocation_total_portfolio
        + npv_general * entry.stock_allocation_total_portfolio;

    float_saturate(stocks_target / savings_portfolio_balance)
}

pub struct MonthResult {
    pub withdrawals_from_savings_portfolio_rate: f64,
    pub balance_ending: f64,
}

// Port of tpaw::_single_month::fn. `expected_run_data` is None for the
// expected run. Returns the computed expected-run data when this is the
// expected run and `write` is true.
#[allow(clippy::too_many_arguments)]
pub fn tpaw_single_month(
    write: bool,
    month_index: usize,
    balance_starting: f64,
    p: &TpawParams,
    returns: &StocksAndBondsF64,
    entry: &TpawEntry,
    expected_run_data: Option<&TpawExpectedRunData>,
    output: Option<&mut RunOutput>,
) -> (MonthResult, Option<TpawExpectedRunData>) {
    let is_expected_run = expected_run_data.is_none();
    let withdrawal_started = month_index >= p.withdrawal_start_month as usize;

    // Step 1: Precomputation at start.
    let precomputation_at_start = get_precomputation_at_start(
        balance_starting,
        entry,
        p.income_by_mfn[month_index],
        p.essential_expense_by_mfn[month_index],
        p.discretionary_expense_by_mfn[month_index],
        expected_run_data,
    );

    // Step 2: Data for expected run (if needed).
    let computed_expected_run_data = if is_expected_run && write {
        Some(get_expected_run_data(
            entry.stock_allocation_total_portfolio,
            entry.legacy_stock_allocation,
            precomputation_at_start.wealth,
            &precomputation_at_start,
        ))
    } else {
        None
    };

    // Step 3: Target withdrawals before ceiling and floor.
    let target_withdrawals_before_ceiling_and_floor =
        get_target_withdrawals_assuming_no_ceiling_or_floor(
            withdrawal_started,
            p.essential_expense_by_mfn[month_index],
            p.discretionary_expense_by_mfn[month_index],
            entry.cumulative_1_plus_g_over_1_plus_r,
            precomputation_at_start.expenses_scale_discretionary,
            precomputation_at_start.npv_scaled_general,
        );

    // Step 4: Apply ceiling and floor.
    let target_withdrawals = apply_withdrawal_ceiling_and_floor(
        &target_withdrawals_before_ceiling_and_floor,
        // Note: NOT the scaled discretionary expense.
        p.discretionary_expense_by_mfn[month_index],
        &p.spending_ceiling,
        &p.spending_floor,
        withdrawal_started,
    );

    // Step 5: Apply contributions and withdrawals.
    let after = apply_contributions_and_withdrawals(
        balance_starting,
        p.income_by_mfn[month_index],
        &target_withdrawals,
    );

    // Step 5.5: Handle NaN/Inf withdrawal rate by re-running with a tiny
    // balance.
    let withdrawals_from_savings_portfolio_rate = if !after
        .withdrawals
        .from_savings_portfolio_rate_or_nan_or_inf
        .is_finite()
    {
        tpaw_single_month(
            false,
            month_index,
            0.000001,
            p,
            returns,
            entry,
            expected_run_data,
            None,
        )
        .0
        .withdrawals_from_savings_portfolio_rate
    } else {
        after.withdrawals.from_savings_portfolio_rate_or_nan_or_inf
    };

    // Step 6: Stock allocation.
    let stock_allocation = get_stock_allocation(
        entry,
        precomputation_at_start.expenses_scale_discretionary,
        precomputation_at_start.expenses_scale_legacy,
        after.balance,
    );

    // Step 7: Apply allocation.
    let at_end = apply_allocation(
        stock_allocation,
        returns,
        after.balance,
        entry.npv_income_without_current_month,
    );

    // Step 8: Write results.
    if write && !is_expected_run {
        if let Some(output) = output {
            output.write_month(
                month_index,
                balance_starting,
                &after,
                withdrawals_from_savings_portfolio_rate,
                &at_end,
                entry.spending_tilt,
            );
        }
    }

    (
        MonthResult {
            withdrawals_from_savings_portfolio_rate,
            balance_ending: at_end.balance,
        },
        computed_expected_run_data,
    )
}
