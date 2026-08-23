// CPU port of the SPAW strategy:
// - cuda_process_spaw_run_x_mfn_simulated_x_mfn.cu (Entry, computed on the
//   fly), and
// - run_spaw.cu (two-pass expected/normal simulation).

use crate::cuda_bridge::OptCURRENCY;

use super::run_common::{
    apply_allocation, apply_contributions_and_withdrawals, apply_withdrawal_ceiling_and_floor,
    MonthlyAndAnnual, RunOutput, StocksAndBondsF64, TargetWithdrawals,
};

pub struct SpawParams<'a> {
    pub num_months: usize,
    pub num_months_to_simulate: usize,
    pub current_portfolio_balance: f64,
    pub withdrawal_start_month: u32,
    pub spending_ceiling: OptCURRENCY,
    pub spending_floor: OptCURRENCY,
    pub income_by_mfn: &'a [f64],
    pub essential_expense_by_mfn: &'a [f64],
    pub discretionary_expense_by_mfn: &'a [f64],
    pub stock_allocation_savings_portfolio_by_mfn: &'a [f64],
    pub spending_tilt_by_mfn: &'a [f64],
    pub legacy: f64,
}

// Cuda_Processed_SPAW_Run_x_MFNSimulated_x_MFN::Entry.
#[derive(Clone, Copy, Debug)]
pub struct SpawEntry {
    pub npv_income_bond_rate_without_current_month: f64,
    pub npv_income_portfolio_rate_without_current_month: f64,
    pub npv_essential_expenses_without_current_month: f64,
    pub npv_discretionary_expenses_without_current_month: f64,
    pub npv_legacy: f64,
    pub cumulative_1_plus_g_over_1_plus_r: f64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct SpawExpectedRunData {
    pub wealth_minus_npv_essential_at_start: f64,
}

pub fn spaw_entry(
    p: &SpawParams,
    month_index: usize,
    expected_returns: &MonthlyAndAnnual,
) -> SpawEntry {
    let monthly_equity_premium =
        expected_returns.monthly.stocks - expected_returns.monthly.bonds;
    let one_over_1p_bonds = 1.0 / (1.0 + expected_returns.monthly.bonds);

    let mut npv_income_bond_rate_with = 0.0f64;
    let mut npv_income_portfolio_rate_with = 0.0f64;
    let mut npv_essential_expense_with = 0.0f64;
    let mut npv_discretionary_expense_with = 0.0f64;
    let mut npv_legacy = p.legacy;
    let mut cumulative_1_plus_g_over_1_plus_r = 0.0f64;

    for ii in (month_index..p.num_months).rev() {
        let one_plus_r_portfolio = 1.0
            + (monthly_equity_premium * p.stock_allocation_savings_portfolio_by_mfn[ii]
                + expected_returns.monthly.bonds);
        let one_over_one_plus_r_portfolio = 1.0 / one_plus_r_portfolio;

        npv_income_bond_rate_with =
            npv_income_bond_rate_with * one_over_1p_bonds + p.income_by_mfn[ii];
        npv_income_portfolio_rate_with =
            npv_income_portfolio_rate_with * one_over_one_plus_r_portfolio + p.income_by_mfn[ii];
        npv_essential_expense_with = npv_essential_expense_with * one_over_one_plus_r_portfolio
            + p.essential_expense_by_mfn[ii];
        npv_discretionary_expense_with = npv_discretionary_expense_with
            * one_over_one_plus_r_portfolio
            + p.discretionary_expense_by_mfn[ii];
        npv_legacy *= one_over_one_plus_r_portfolio;

        let one_plus_g_over_1_plus_r =
            (p.spending_tilt_by_mfn[ii] + 1.0) * one_over_one_plus_r_portfolio;
        cumulative_1_plus_g_over_1_plus_r =
            cumulative_1_plus_g_over_1_plus_r * one_plus_g_over_1_plus_r + 1.0;
    }

    SpawEntry {
        npv_income_bond_rate_without_current_month: npv_income_bond_rate_with
            - p.income_by_mfn[month_index],
        npv_income_portfolio_rate_without_current_month: npv_income_portfolio_rate_with
            - p.income_by_mfn[month_index],
        npv_essential_expenses_without_current_month: npv_essential_expense_with
            - p.essential_expense_by_mfn[month_index],
        npv_discretionary_expenses_without_current_month: npv_discretionary_expense_with
            - p.discretionary_expense_by_mfn[month_index],
        npv_legacy,
        cumulative_1_plus_g_over_1_plus_r,
    }
}

pub struct MonthResult {
    pub withdrawals_from_savings_portfolio_rate: f64,
    pub balance_ending: f64,
}

// Port of spaw::_single_month::fn. `expected_run_data` is None for the
// expected run. Returns the computed expected-run data when this is the
// expected run and `write` is true.
#[allow(clippy::too_many_arguments)]
pub fn spaw_single_month(
    write: bool,
    month_index: usize,
    balance_starting: f64,
    p: &SpawParams,
    returns: &StocksAndBondsF64,
    entry: &SpawEntry,
    expected_run_data: Option<&SpawExpectedRunData>,
    output: Option<&mut RunOutput>,
) -> (MonthResult, Option<SpawExpectedRunData>) {
    let is_expected_run = expected_run_data.is_none();
    let withdrawal_started = month_index >= p.withdrawal_start_month as usize;

    let current_month_income = p.income_by_mfn[month_index];
    let current_month_essential_expense = p.essential_expense_by_mfn[month_index];
    let current_month_discretionary_expense = p.discretionary_expense_by_mfn[month_index];

    // Step 1: Precomputation at start.
    let npv_income_portfolio_rate_with_current_month =
        entry.npv_income_portfolio_rate_without_current_month + current_month_income;
    let npv_essential_expenses_with_current_month =
        entry.npv_essential_expenses_without_current_month + current_month_essential_expense;
    let npv_discretionary_expenses_with_current_month =
        entry.npv_discretionary_expenses_without_current_month
            + current_month_discretionary_expense;
    let wealth_minus_npv_essential_at_start = balance_starting
        // Intentionally using portfolio rate and not bond rate.
        + npv_income_portfolio_rate_with_current_month
        - npv_essential_expenses_with_current_month;

    // Step 2: Data for expected run (if needed).
    let computed_expected_run_data = if is_expected_run && write {
        Some(SpawExpectedRunData {
            wealth_minus_npv_essential_at_start,
        })
    } else {
        None
    };

    // Step 3: Target withdrawals before ceiling and floor.
    let scale = match expected_run_data {
        None => 1.0,
        Some(expected) => {
            if expected.wealth_minus_npv_essential_at_start == 0.0 {
                1.0
            } else {
                wealth_minus_npv_essential_at_start
                    / expected.wealth_minus_npv_essential_at_start
            }
        }
    };
    let general = if !withdrawal_started {
        0.0
    } else {
        (((-npv_discretionary_expenses_with_current_month - entry.npv_legacy) * scale
            + wealth_minus_npv_essential_at_start)
            / entry.cumulative_1_plus_g_over_1_plus_r)
            .max(0.0)
    };
    let target_withdrawals_before_ceiling_and_floor = TargetWithdrawals {
        essential: current_month_essential_expense,
        discretionary: (current_month_discretionary_expense * scale).max(0.0),
        general,
    };

    // Step 4: Apply ceiling and floor.
    let target_withdrawals = apply_withdrawal_ceiling_and_floor(
        &target_withdrawals_before_ceiling_and_floor,
        // Note: NOT the scaled discretionary expense.
        current_month_discretionary_expense,
        &p.spending_ceiling,
        &p.spending_floor,
        withdrawal_started,
    );

    // Step 5: Apply contributions and withdrawals.
    let after = apply_contributions_and_withdrawals(
        balance_starting,
        current_month_income,
        &target_withdrawals,
    );

    // Step 5.5: Handle NaN/Inf withdrawal rate.
    let withdrawals_from_savings_portfolio_rate = if !after
        .withdrawals
        .from_savings_portfolio_rate_or_nan_or_inf
        .is_finite()
    {
        spaw_single_month(
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

    // Step 6: Stock allocation (from the glide path).
    let stock_allocation = p.stock_allocation_savings_portfolio_by_mfn[month_index];

    // Step 7: Apply allocation.
    let at_end = apply_allocation(
        stock_allocation,
        returns,
        after.balance,
        entry.npv_income_bond_rate_without_current_month,
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
                0.0, // tpaw_spending_tilt
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
