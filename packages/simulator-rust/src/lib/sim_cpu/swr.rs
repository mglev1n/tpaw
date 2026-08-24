// CPU port of the SWR strategy:
// - cuda_process_swr_run_x_mfn_simulated_x_mfn.cu (Entry, computed on the
//   fly), and
// - run_swr.cu (single-pass simulation with carried target withdrawal).

use crate::cuda_bridge::{
    OptCURRENCY, PlanParamsCuda_Risk_SWR_WithdrawalType,
    PlanParamsCuda_Risk_SWR_WithdrawalType_Percent,
};

use super::run_common::{
    apply_allocation, apply_contributions_and_withdrawals, apply_withdrawal_ceiling_and_floor,
    MonthlyAndAnnual, RunOutput, StocksAndBondsF64, TargetWithdrawals,
};

pub struct SwrParams<'a> {
    pub num_months: usize,
    pub num_months_to_simulate: usize,
    pub current_portfolio_balance: f64,
    pub withdrawal_start_month: u32,
    pub withdrawal_type: PlanParamsCuda_Risk_SWR_WithdrawalType,
    pub withdrawal_as_percent_or_amount: f64,
    pub income_by_mfn: &'a [f64],
    pub essential_expense_by_mfn: &'a [f64],
    pub discretionary_expense_by_mfn: &'a [f64],
    pub stock_allocation_savings_portfolio_by_mfn: &'a [f64],
}

// Cuda_Processed_SWR_Run_x_MFNSimulated_x_MFN::Entry.
#[derive(Clone, Copy, Debug)]
pub struct SwrEntry {
    pub npv_income_bond_rate_without_current_month: f64,
}

pub fn swr_entry(
    p: &SwrParams,
    month_index: usize,
    expected_returns: &MonthlyAndAnnual,
) -> SwrEntry {
    let one_over_1p_bonds = 1.0 / (1.0 + expected_returns.monthly.bonds);
    let mut npv_income_bond_rate_with = 0.0f64;
    for ii in (month_index..p.num_months).rev() {
        npv_income_bond_rate_with =
            npv_income_bond_rate_with * one_over_1p_bonds + p.income_by_mfn[ii];
    }
    SwrEntry {
        npv_income_bond_rate_without_current_month: npv_income_bond_rate_with
            - p.income_by_mfn[month_index],
    }
}

pub struct MonthResult {
    pub withdrawals_from_savings_portfolio_rate: f64,
    pub balance_ending: f64,
    pub target_withdrawal_general: f64,
}

// Port of swr::_single_month::fn.
#[allow(clippy::too_many_arguments)]
pub fn swr_single_month(
    write: bool,
    month_index: usize,
    balance_starting: f64,
    prev_target_withdrawal_general: f64,
    p: &SwrParams,
    returns: &StocksAndBondsF64,
    entry: &SwrEntry,
    output: Option<&mut RunOutput>,
) -> MonthResult {
    let withdrawal_started = month_index >= p.withdrawal_start_month as usize;
    let withdrawal_start_month = p.withdrawal_start_month as usize;

    let current_month_income = p.income_by_mfn[month_index];
    let current_month_essential_expense = p.essential_expense_by_mfn[month_index];
    let current_month_discretionary_expense = p.discretionary_expense_by_mfn[month_index];

    // Step 3: Target withdrawals before ceiling and floor.
    let general = if month_index < withdrawal_start_month {
        0.0
    } else if month_index > withdrawal_start_month {
        prev_target_withdrawal_general
    } else if p.withdrawal_type == PlanParamsCuda_Risk_SWR_WithdrawalType_Percent {
        // balance_starting when month_index == withdrawal_start_month is the
        // balance at the start of retirement.
        (balance_starting * p.withdrawal_as_percent_or_amount).max(0.0)
    } else {
        p.withdrawal_as_percent_or_amount
    };
    let target_withdrawals_before_ceiling_and_floor = TargetWithdrawals {
        essential: current_month_essential_expense,
        discretionary: current_month_discretionary_expense,
        general,
    };

    // Step 4: No ceiling or floor for SWR.
    let unset = OptCURRENCY {
        is_set: 0,
        opt_value: 0.0,
    };
    let target_withdrawals = apply_withdrawal_ceiling_and_floor(
        &target_withdrawals_before_ceiling_and_floor,
        current_month_discretionary_expense,
        &unset,
        &unset,
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
        swr_single_month(
            false,
            month_index,
            0.000001,
            prev_target_withdrawal_general,
            p,
            returns,
            entry,
            None,
        )
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
    if write {
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

    MonthResult {
        withdrawals_from_savings_portfolio_rate,
        balance_ending: at_end.balance,
        target_withdrawal_general: target_withdrawals.general,
    }
}
