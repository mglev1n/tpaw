// CPU port of packages/simulator-cuda/src/simulate/run/run_common.h and
// src/utils/account_for_withdrawal.h.

use crate::cuda_bridge::OptCURRENCY;

#[derive(Clone, Copy, Debug)]
pub struct StocksAndBondsF64 {
    pub stocks: f64,
    pub bonds: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct MonthlyAndAnnual {
    pub monthly: StocksAndBondsF64,
    pub annual: StocksAndBondsF64,
}

pub struct AccountForWithdrawal {
    pub balance: f64,
    pub insufficient_funds: bool,
}

impl AccountForWithdrawal {
    pub fn new(balance: f64) -> Self {
        AccountForWithdrawal {
            balance,
            insufficient_funds: false,
        }
    }

    pub fn withdraw(&mut self, amount: f64) -> f64 {
        if self.balance < amount {
            // Insufficient funds means running out by at least $1, to prevent
            // hypersensitivity to floating point imprecision.
            if amount - self.balance > 1.0 {
                self.insufficient_funds = true;
            }
            let amount_withdrawn = self.balance;
            self.balance = 0.0;
            amount_withdrawn
        } else {
            self.balance -= amount;
            amount
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TargetWithdrawals {
    pub essential: f64,
    pub discretionary: f64,
    pub general: f64,
}

pub fn apply_withdrawal_ceiling_and_floor(
    target: &TargetWithdrawals,
    curr_month_discretionary_expense: f64,
    spending_ceiling: &OptCURRENCY,
    spending_floor: &OptCURRENCY,
    withdrawal_started: bool,
) -> TargetWithdrawals {
    let mut general = target.general;
    let mut discretionary = target.discretionary;

    if spending_ceiling.is_set != 0 {
        discretionary = discretionary.min(curr_month_discretionary_expense);
        general = general.min(spending_ceiling.opt_value);
    }

    if spending_floor.is_set != 0 {
        discretionary = discretionary.max(curr_month_discretionary_expense);
        if withdrawal_started {
            general = general.max(spending_floor.opt_value);
        }
    }

    TargetWithdrawals {
        essential: target.essential,
        discretionary,
        general,
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Withdrawals {
    pub essential: f64,
    pub discretionary: f64,
    pub general: f64,
    pub total: f64,
    pub from_savings_portfolio_rate_or_nan_or_inf: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct AfterContributionsAndWithdrawals {
    pub contributions: f64,
    pub withdrawals: Withdrawals,
    pub balance: f64,
    pub insufficient_funds: bool,
}

pub fn apply_contributions_and_withdrawals(
    balance_starting: f64,
    contributions: f64,
    target_withdrawals: &TargetWithdrawals,
) -> AfterContributionsAndWithdrawals {
    let mut account = AccountForWithdrawal::new(balance_starting + contributions);
    let withdrawal_essential = account.withdraw(target_withdrawals.essential);
    let withdrawal_discretionary = account.withdraw(target_withdrawals.discretionary);
    let withdrawal_general = account.withdraw(target_withdrawals.general);
    let withdraw_total = withdrawal_essential + withdrawal_discretionary + withdrawal_general;

    let from_contributions = withdraw_total.min(contributions);
    let from_savings_portfolio = withdraw_total - from_contributions;
    // 0/0 is NaN, but !0/0 is Inf.
    let from_savings_portfolio_rate_or_nan_or_inf = from_savings_portfolio / balance_starting;

    AfterContributionsAndWithdrawals {
        contributions,
        withdrawals: Withdrawals {
            essential: withdrawal_essential,
            discretionary: withdrawal_discretionary,
            general: withdrawal_general,
            total: withdraw_total,
            from_savings_portfolio_rate_or_nan_or_inf,
        },
        balance: account.balance,
        insufficient_funds: account.insufficient_funds,
    }
}

#[derive(Clone, Copy, Debug)]
pub struct End {
    pub stock_allocation_percent_before_returns: f64,
    pub stock_allocation_amount_before_returns: f64,
    pub balance: f64,
    pub stock_allocation_on_total_portfolio_or_zero_if_no_wealth: f64,
}

pub fn apply_allocation(
    stock_allocation_percent: f64,
    return_rate: &StocksAndBondsF64,
    balance_after_contributions_and_withdrawals: f64,
    npv_income_without_current_month: f64,
) -> End {
    let stock_allocation_amount =
        balance_after_contributions_and_withdrawals * stock_allocation_percent;
    let bonds_allocation_amount =
        balance_after_contributions_and_withdrawals - stock_allocation_amount;
    let stock_allocation_amount_after_return =
        stock_allocation_amount * (1.0 + return_rate.stocks);
    let balance = (1.0 + return_rate.bonds)
        .mul_add(bonds_allocation_amount, stock_allocation_amount_after_return);

    let stock_allocation_on_total_portfolio = stock_allocation_amount
        / (balance_after_contributions_and_withdrawals + npv_income_without_current_month);
    End {
        stock_allocation_percent_before_returns: stock_allocation_percent,
        stock_allocation_amount_before_returns: stock_allocation_amount,
        balance,
        stock_allocation_on_total_portfolio_or_zero_if_no_wealth:
            if stock_allocation_on_total_portfolio.is_finite() {
                stock_allocation_on_total_portfolio
            } else {
                0.0
            },
    }
}

// Per-run result columns (the CPU analog of RunResultPadded, without padding).
pub struct RunOutput {
    pub balance_start: Vec<f64>,
    pub withdrawals_essential: Vec<f64>,
    pub withdrawals_discretionary: Vec<f64>,
    pub withdrawals_general: Vec<f64>,
    pub withdrawals_total: Vec<f64>,
    pub withdrawals_from_savings_portfolio_rate: Vec<f64>,
    pub after_withdrawals_allocation_savings_portfolio: Vec<f64>,
    pub after_withdrawals_allocation_total_portfolio_or_zero_if_no_wealth: Vec<f64>,
    pub tpaw_spending_tilt: Vec<f64>,
    pub num_insufficient_fund_months: u32,
    pub ending_balance: f64,
}

impl RunOutput {
    pub fn new(num_months_to_simulate: usize) -> Self {
        RunOutput {
            balance_start: vec![0.0; num_months_to_simulate],
            withdrawals_essential: vec![0.0; num_months_to_simulate],
            withdrawals_discretionary: vec![0.0; num_months_to_simulate],
            withdrawals_general: vec![0.0; num_months_to_simulate],
            withdrawals_total: vec![0.0; num_months_to_simulate],
            withdrawals_from_savings_portfolio_rate: vec![0.0; num_months_to_simulate],
            after_withdrawals_allocation_savings_portfolio: vec![0.0; num_months_to_simulate],
            after_withdrawals_allocation_total_portfolio_or_zero_if_no_wealth: vec![
                0.0;
                num_months_to_simulate
            ],
            tpaw_spending_tilt: vec![0.0; num_months_to_simulate],
            num_insufficient_fund_months: 0,
            ending_balance: 0.0,
        }
    }

    pub fn write_month(
        &mut self,
        month_index: usize,
        balance_starting: f64,
        after: &AfterContributionsAndWithdrawals,
        withdrawals_from_savings_portfolio_rate: f64,
        at_end: &End,
        spending_tilt: f64,
    ) {
        self.balance_start[month_index] = balance_starting;
        self.withdrawals_essential[month_index] = after.withdrawals.essential;
        self.withdrawals_discretionary[month_index] = after.withdrawals.discretionary;
        self.withdrawals_general[month_index] = after.withdrawals.general;
        self.withdrawals_total[month_index] = after.withdrawals.total;
        self.withdrawals_from_savings_portfolio_rate[month_index] =
            withdrawals_from_savings_portfolio_rate;
        self.after_withdrawals_allocation_savings_portfolio[month_index] =
            at_end.stock_allocation_percent_before_returns;
        self.after_withdrawals_allocation_total_portfolio_or_zero_if_no_wealth[month_index] =
            at_end.stock_allocation_on_total_portfolio_or_zero_if_no_wealth;
        self.tpaw_spending_tilt[month_index] = spending_tilt;
        if after.insufficient_funds {
            self.num_insufficient_fund_months += 1;
        }
        self.ending_balance = at_end.balance;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn opt(is_set: bool, value: f64) -> OptCURRENCY {
        OptCURRENCY {
            is_set: if is_set { 1 } else { 0 },
            opt_value: value,
        }
    }

    // Ports of run_common.cu doctests.
    #[test]
    fn ceiling_and_floor() {
        let target = TargetWithdrawals {
            essential: 1000.0,
            discretionary: 2000.0,
            general: 3000.0,
        };
        let none = apply_withdrawal_ceiling_and_floor(
            &target,
            500.0,
            &opt(false, 300.0),
            &opt(false, 500.0),
            true,
        );
        assert_eq!(
            (none.essential, none.discretionary, none.general),
            (1000.0, 2000.0, 3000.0)
        );

        let ceiling = apply_withdrawal_ceiling_and_floor(
            &target,
            500.0,
            &opt(true, 600.0),
            &opt(false, 300.0),
            true,
        );
        assert_eq!(
            (ceiling.essential, ceiling.discretionary, ceiling.general),
            (1000.0, 500.0, 600.0)
        );

        let floor_started = apply_withdrawal_ceiling_and_floor(
            &target,
            500.0,
            &opt(false, 600.0),
            &opt(true, 3010.0),
            true,
        );
        assert_eq!(
            (
                floor_started.essential,
                floor_started.discretionary,
                floor_started.general
            ),
            (1000.0, 2000.0, 3010.0)
        );

        let target_not_started = TargetWithdrawals {
            general: 0.0,
            ..target
        };
        let floor_not_started = apply_withdrawal_ceiling_and_floor(
            &target_not_started,
            500.0,
            &opt(false, 600.0),
            &opt(true, 3010.0),
            false,
        );
        assert_eq!(
            (
                floor_not_started.essential,
                floor_not_started.discretionary,
                floor_not_started.general
            ),
            (1000.0, 2000.0, 0.0)
        );
    }

    #[test]
    fn contributions_and_withdrawals() {
        let target = TargetWithdrawals {
            essential: 1000.0,
            discretionary: 2000.0,
            general: 3000.0,
        };
        let sufficient = apply_contributions_and_withdrawals(10000.0, 1000.0, &target);
        assert_eq!(sufficient.withdrawals.total, 6000.0);
        assert_eq!(sufficient.withdrawals.general, 3000.0);
        assert!(
            (sufficient.withdrawals.from_savings_portfolio_rate_or_nan_or_inf
                - (6000.0 - 1000.0) / 10000.0)
                .abs()
                < 1e-12
        );
        assert_eq!(sufficient.balance, 10000.0 + 1000.0 - 6000.0);
        assert!(!sufficient.insufficient_funds);

        let insufficient = apply_contributions_and_withdrawals(3000.0, 1000.0, &target);
        assert_eq!(insufficient.withdrawals.general, 1000.0);
        assert_eq!(insufficient.withdrawals.total, 4000.0);
        assert!(
            (insufficient.withdrawals.from_savings_portfolio_rate_or_nan_or_inf
                - (4000.0 - 1000.0) / 3000.0)
                .abs()
                < 1e-12
        );
        assert_eq!(insufficient.balance, 0.0);
        assert!(insufficient.insufficient_funds);
    }

    #[test]
    fn allocation() {
        let result = apply_allocation(
            0.5,
            &StocksAndBondsF64 {
                stocks: 0.05,
                bonds: 0.03,
            },
            1000.0,
            100.0,
        );
        let stocks_amount = 1000.0 * 0.5;
        assert_eq!(result.stock_allocation_percent_before_returns, 0.5);
        assert!((result.stock_allocation_amount_before_returns - stocks_amount).abs() < 1e-9);
        assert!(
            (result.balance - (stocks_amount * 1.05 + (1000.0 - stocks_amount) * 1.03)).abs()
                < 1e-9
        );
        assert!(
            (result.stock_allocation_on_total_portfolio_or_zero_if_no_wealth
                - stocks_amount / 1100.0)
                .abs()
                < 1e-12
        );
    }
}
