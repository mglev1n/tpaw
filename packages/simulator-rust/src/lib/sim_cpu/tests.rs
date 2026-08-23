// End-to-end tests for cpu_simulate against closed-form expectations.

use super::cpu_simulate;
use crate::cuda_bridge::*;

struct SimInputs {
    num_months: u32,
    future_savings_by_mfn: Vec<f64>,
    income_during_retirement_by_mfn: Vec<f64>,
    essential_expenses_by_mfn: Vec<f64>,
    discretionary_expenses_by_mfn: Vec<f64>,
    tpaw_rra_by_mfn: Vec<f32>,
    spaw_spending_tilt_by_mfn: Vec<f32>,
    stock_allocation_by_mfn: Vec<f32>,
    percentiles: Vec<u32>,
    historical_returns_series: Vec<HistoricalReturnsCuda>,
}

struct SimOutputs {
    not_arrays: ResultCudaNotArrays,
    balance_start: Vec<f64>,
    withdrawals_essential: Vec<f64>,
    withdrawals_discretionary: Vec<f64>,
    withdrawals_general: Vec<f64>,
    withdrawals_total: Vec<f64>,
    ending_balance: Vec<f64>,
    tpaw_stock_allocation_month_0_by_mfn: Vec<f32>,
}

fn run(inputs: &mut SimInputs, plan_params: &PlanParamsCuda, balance: f64) -> SimOutputs {
    let num_months = inputs.num_months as usize;
    let nms = num_months;
    let n1 = inputs.percentiles.len() * nms;
    let mut balance_start = vec![0.0f64; n1];
    let mut withdrawals_essential = vec![0.0f64; n1];
    let mut withdrawals_discretionary = vec![0.0f64; n1];
    let mut withdrawals_general = vec![0.0f64; n1];
    let mut withdrawals_total = vec![0.0f64; n1];
    let mut rate = vec![0.0f32; n1];
    let mut alloc_savings = vec![0.0f32; n1];
    let mut alloc_total = vec![0.0f32; n1];
    let mut tilt = vec![0.0f32; n1];
    let mut ending_balance = vec![0.0f64; inputs.percentiles.len()];
    let mut alloc_month_0 = vec![0.0f32; num_months];

    let c_arrays = PlanParamsCuda_C_Arrays {
        future_savings_by_mfn: inputs.future_savings_by_mfn.as_mut_ptr(),
        income_during_retirement_by_mfn: inputs.income_during_retirement_by_mfn.as_mut_ptr(),
        essential_expenses_by_mfn: inputs.essential_expenses_by_mfn.as_mut_ptr(),
        discretionary_expenses_by_mfn: inputs.discretionary_expenses_by_mfn.as_mut_ptr(),
        tpaw_rra_including_pos_infinity_by_mfn: inputs.tpaw_rra_by_mfn.as_mut_ptr(),
        spaw_spending_tilt_by_mfn: inputs.spaw_spending_tilt_by_mfn.as_mut_ptr(),
        spaw_and_swr_stock_allocation_savings_portfolio_by_mfn: inputs
            .stock_allocation_by_mfn
            .as_mut_ptr(),
        num_percentiles: inputs.percentiles.len() as u32,
        percentiles: inputs.percentiles.as_mut_ptr(),
        historical_returns_series_len: inputs.historical_returns_series.len() as u32,
        historical_returns_series: inputs.historical_returns_series.as_mut_ptr(),
    };
    let mut out = ResultCudaArrays {
        by_percentile_by_mfn_simulated_percentile_major_balance_start: balance_start.as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_withdrawals_essential:
            withdrawals_essential.as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_withdrawals_discretionary:
            withdrawals_discretionary.as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_withdrawals_general: withdrawals_general
            .as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_withdrawals_total: withdrawals_total
            .as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_withdrawals_from_savings_portfolio_rate:
            rate.as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_after_withdrawals_allocation_savings_portfolio:
            alloc_savings.as_mut_ptr(),
        by_percentile_by_mfn_simulated_percentile_major_after_withdrawals_allocation_total_portfolio_or_zero_if_no_wealth:
            alloc_total.as_mut_ptr(),
        tpaw_by_percentile_by_mfn_simulated_percentile_major_spending_tilt: tilt.as_mut_ptr(),
        by_percentile_ending_balance: ending_balance.as_mut_ptr(),
        tpaw_stock_allocation_total_portfolio_for_month_0_by_mfn: alloc_month_0.as_mut_ptr(),
    };

    let not_arrays =
        unsafe { cpu_simulate(inputs.num_months, balance, plan_params, &c_arrays, &mut out) };

    SimOutputs {
        not_arrays,
        balance_start,
        withdrawals_essential,
        withdrawals_discretionary,
        withdrawals_general,
        withdrawals_total,
        ending_balance,
        tpaw_stock_allocation_month_0_by_mfn: alloc_month_0,
    }
}

fn make_inputs(num_months: u32, monthly_return: f32) -> SimInputs {
    let n = num_months as usize;
    SimInputs {
        num_months,
        future_savings_by_mfn: vec![0.0; n],
        income_during_retirement_by_mfn: vec![0.0; n],
        essential_expenses_by_mfn: vec![0.0; n],
        discretionary_expenses_by_mfn: vec![0.0; n],
        tpaw_rra_by_mfn: vec![4.0; n],
        spaw_spending_tilt_by_mfn: vec![0.0; n],
        stock_allocation_by_mfn: vec![0.5; n],
        percentiles: vec![5, 50, 95],
        historical_returns_series: vec![
            HistoricalReturnsCuda {
                stocks: HistoricalReturnsCuda_Part {
                    returns: monthly_return,
                    expected_return_change: 0.0,
                },
                bonds: HistoricalReturnsCuda_Part {
                    returns: monthly_return,
                    expected_return_change: 0.0,
                },
            };
            100
        ],
    }
}

fn make_plan_params(
    num_months: u32,
    withdrawal_start_month: u32,
    strategy: PlanParamsCuda_Advanced_Strategy,
    num_runs: u32,
    monthly_expected_return: f32,
) -> PlanParamsCuda {
    PlanParamsCuda {
        ages: PlanParamsCuda_Ages {
            simulation_months: PlanParamsCuda_Ages_SimulationMonths {
                num_months,
                withdrawal_start_month,
            },
        },
        adjustments_to_spending: PlanParamsCuda_AdjustmentsToSpending {
            tpaw_and_spaw: PlanParamsCuda_AdjustmentsToSpending_TPAWAndSPAW {
                spending_ceiling: OptCURRENCY {
                    is_set: 0,
                    opt_value: 0.0,
                },
                spending_floor: OptCURRENCY {
                    is_set: 0,
                    opt_value: 0.0,
                },
                legacy: 0.0,
            },
        },
        risk: PlanParamsCuda_Risk {
            tpaw: PlanParamsCuda_Risk_TPAW {
                time_preference: 0.0,
                annual_additional_spending_tilt: 0.0,
                legacy_rra_including_pos_infinity: 5.0,
            },
            swr: PlanParamsCuda_Risk_SWR {
                withdrawal_type: PlanParamsCuda_Risk_SWR_WithdrawalType_Percent,
                withdrawal_as_percent_or_amount: 0.004,
            },
        },
        advanced: PlanParamsCuda_Advanced {
            return_stats_for_planning: PlanParamsCuda_Advanced_ReturnStatsForPlanning {
                expected_returns_at_month_0: StocksAndBondsFLOAT {
                    stocks: monthly_expected_return,
                    bonds: monthly_expected_return,
                },
                annual_empirical_log_variance_stocks: 0.01,
            },
            sampling: PlanParamsCuda_Advanced_Sampling {
                type_: PlanParamsCuda_Advanced_Sampling_Type_MonteCarloSampling,
                monte_carlo_or_historical: PlanParamsCuda_Advanced_Sampling_MonteCarloOrHistorical {
                    monte_carlo: PlanParamsCuda_Advanced_Sampling_MonteCarlo {
                        seed: 1234,
                        num_runs,
                        block_size: 12,
                        stagger_run_starts: 1,
                    },
                },
            },
            strategy,
        },
    }
}

#[test]
fn swr_zero_returns_closed_form() {
    // Zero returns everywhere, no income or expenses, 0.4%/month SWR from
    // month 0: balance declines by exactly 100000 * 0.004 = 400 every month,
    // identically in every run.
    let num_months = 120u32;
    let mut inputs = make_inputs(num_months, 0.0);
    let plan_params = make_plan_params(
        num_months,
        0,
        PlanParamsCuda_Advanced_Strategy_Strategy_SWR,
        50,
        0.0,
    );
    let outputs = run(&mut inputs, &plan_params, 100_000.0);

    assert_eq!(outputs.not_arrays.num_runs, 50);
    assert_eq!(outputs.not_arrays.num_runs_with_insufficient_funds, 0);
    let nms = num_months as usize;
    for pi in 0..inputs.percentiles.len() {
        for m in 0..nms {
            let expected_balance = 100_000.0 - 400.0 * m as f64;
            assert!(
                (outputs.balance_start[pi * nms + m] - expected_balance).abs() < 1e-6,
                "balance at percentile {} month {}: {} != {}",
                pi,
                m,
                outputs.balance_start[pi * nms + m],
                expected_balance
            );
            assert!((outputs.withdrawals_general[pi * nms + m] - 400.0).abs() < 1e-6);
            assert_eq!(outputs.withdrawals_essential[pi * nms + m], 0.0);
            assert_eq!(outputs.withdrawals_discretionary[pi * nms + m], 0.0);
            assert!((outputs.withdrawals_total[pi * nms + m] - 400.0).abs() < 1e-6);
        }
        let expected_ending = 100_000.0 - 400.0 * nms as f64;
        assert!((outputs.ending_balance[pi] - expected_ending).abs() < 1e-6);
    }
}

#[test]
fn tpaw_all_percentiles_equal_with_constant_returns() {
    // Every entry of the historical series is the same constant return with no
    // expected-return drift, so all runs are identical and every percentile
    // must coincide. TPAW with no legacy or expenses amortizes the portfolio
    // to ~0 by the end.
    let num_months = 240u32;
    let monthly_return = 0.004f32; // ~4.9%/yr
    let mut inputs = make_inputs(num_months, monthly_return);
    let plan_params = make_plan_params(
        num_months,
        0,
        PlanParamsCuda_Advanced_Strategy_Strategy_TPAW,
        100,
        monthly_return,
    );
    let outputs = run(&mut inputs, &plan_params, 100_000.0);

    assert_eq!(outputs.not_arrays.num_runs, 100);
    assert_eq!(outputs.not_arrays.num_runs_with_insufficient_funds, 0);
    // Legacy is 0, so its NPV is 0.
    assert_eq!(
        outputs.not_arrays.tpaw_net_present_value_exact_month_0_legacy,
        0.0
    );

    let nms = num_months as usize;
    let p = inputs.percentiles.len();
    for m in 0..nms {
        let p5 = outputs.balance_start[m];
        let p50 = outputs.balance_start[nms + m];
        let p95 = outputs.balance_start[(p - 1) * nms + m];
        assert!(p5.is_finite());
        assert_eq!(p5, p50);
        assert_eq!(p50, p95);
        // Withdrawals happen every month (withdrawal_start_month = 0) and the
        // balance is amortized, so withdrawals are positive and the balance
        // never grows above the (return-compounded) start.
        assert!(outputs.withdrawals_general[m] > 0.0, "month {}", m);
    }
    // Fully amortized: ends near zero (and exactly equal across percentiles).
    assert!(outputs.ending_balance[0] >= 0.0);
    assert!(outputs.ending_balance[0] < 1.0);
    assert_eq!(outputs.ending_balance[0], outputs.ending_balance[p - 1]);

    // Zero equity premium => stock allocation 0 for every month.
    for &a in &outputs.tpaw_stock_allocation_month_0_by_mfn {
        assert_eq!(a, 0.0);
    }
}

#[test]
fn spaw_all_percentiles_equal_with_constant_returns() {
    let num_months = 240u32;
    let monthly_return = 0.003f32;
    let mut inputs = make_inputs(num_months, monthly_return);
    // Give it some income and expenses to exercise those paths.
    for m in 0..120 {
        inputs.future_savings_by_mfn[m] = 1000.0;
    }
    for m in 120..240 {
        inputs.essential_expenses_by_mfn[m] = 500.0;
        inputs.discretionary_expenses_by_mfn[m] = 200.0;
    }
    let plan_params = make_plan_params(
        num_months,
        120,
        PlanParamsCuda_Advanced_Strategy_Strategy_SPAW,
        50,
        monthly_return,
    );
    let outputs = run(&mut inputs, &plan_params, 50_000.0);

    assert_eq!(outputs.not_arrays.num_runs, 50);
    let nms = num_months as usize;
    for m in 0..nms {
        assert_eq!(outputs.balance_start[m], outputs.balance_start[2 * nms + m]);
        assert!(outputs.balance_start[m].is_finite());
    }
    // Before withdrawal start, essential/discretionary/general withdrawals are
    // paid from income, general is 0.
    for m in 0..120 {
        assert_eq!(outputs.withdrawals_general[m], 0.0);
        assert_eq!(outputs.withdrawals_essential[m], 0.0);
    }
    // After withdrawal start, essential expenses are withdrawn in full.
    for m in 120..nms {
        assert!((outputs.withdrawals_essential[m] - 500.0).abs() < 1e-9);
    }
}
