// Pure-Rust CPU implementation of the simulator engine, a drop-in replacement
// for the CUDA backend (packages/simulator-cuda). `cpu_simulate` has the same
// signature as `cuda_bridge::cuda_simulate` so the caller in simulate.rs can
// select the backend with a feature flag.
//
// Numerics: this port uses f64 throughout, i.e. the CUDA codebase's
// "REPLICATION MODE" (see packages/simulator-cuda/src/public_headers/
// numeric_types.h) rather than the f32 "EFFICIENT MODE" the GPU runs in
// production. Monte Carlo index sequences are bit-exact with the GPU
// (see xorwow.rs / sampling.rs); floating point results agree to within
// f32 precision.

pub mod mertons;
pub mod run_common;
pub mod sampling;
pub mod spaw;
pub mod swr;
pub mod tpaw;
pub mod xorwow;

#[cfg(test)]
mod tests;

use rayon::prelude::*;

use crate::cuda_bridge::{
    HistoricalReturnsCuda, PlanParamsCuda, PlanParamsCuda_Advanced_Sampling_Type_HistoricalSampling,
    PlanParamsCuda_Advanced_Sampling_Type_MonteCarloSampling,
    PlanParamsCuda_Advanced_Strategy_Strategy_SPAW, PlanParamsCuda_Advanced_Strategy_Strategy_SWR,
    PlanParamsCuda_Advanced_Strategy_Strategy_TPAW, PlanParamsCuda_C_Arrays, ResultCudaArrays,
    ResultCudaNotArrays,
};

use mertons::monthly_to_annual_rate;
use run_common::{MonthlyAndAnnual, RunOutput, StocksAndBondsF64};
use sampling::{get_num_runs, make_index_gen, IndexGen, SamplingSpec};
use spaw::{spaw_entry, spaw_single_month, SpawExpectedRunData, SpawParams};
use swr::{swr_entry, swr_single_month, SwrParams};
use tpaw::{
    tpaw_entry, tpaw_single_month, tpaw_stock_allocation_total_portfolio_for_month_0_by_mfn,
    TpawExpectedRunData, TpawParams,
};

// Walks a run's sampled path through the historical returns series, yielding
// per month the historical returns and the accumulated expected returns
// (port of cuda_process_historical_returns.cu).
struct ReturnsPath<'a> {
    series: &'a [HistoricalReturnsCuda],
    gen: IndexGen,
    curr_expected: StocksAndBondsF64,
}

impl<'a> ReturnsPath<'a> {
    fn new(
        series: &'a [HistoricalReturnsCuda],
        gen: IndexGen,
        expected_returns_at_month_0: StocksAndBondsF64,
    ) -> Self {
        ReturnsPath {
            series,
            gen,
            curr_expected: expected_returns_at_month_0,
        }
    }

    fn next(&mut self) -> (StocksAndBondsF64, MonthlyAndAnnual) {
        let h = &self.series[self.gen.next() as usize];
        let historical = StocksAndBondsF64 {
            stocks: h.stocks.returns as f64,
            bonds: h.bonds.returns as f64,
        };
        self.curr_expected.stocks += h.stocks.expected_return_change as f64;
        self.curr_expected.bonds += h.bonds.expected_return_change as f64;
        let expected = MonthlyAndAnnual {
            monthly: self.curr_expected,
            annual: StocksAndBondsF64 {
                stocks: monthly_to_annual_rate(self.curr_expected.stocks),
                bonds: monthly_to_annual_rate(self.curr_expected.bonds),
            },
        };
        (historical, expected)
    }
}

fn uniquify(values: &[f64]) -> (Vec<f64>, Vec<u32>) {
    let mut unique: Vec<f64> = Vec::new();
    let indices = values
        .iter()
        .map(|&v| {
            match unique.iter().position(|&u| u.to_bits() == v.to_bits()) {
                Some(i) => i as u32,
                None => {
                    unique.push(v);
                    (unique.len() - 1) as u32
                }
            }
        })
        .collect();
    (unique, indices)
}

// Port of pick_percentiles.cu::get_percentile_index (nearest rank on the
// unpadded run count).
fn get_percentile_index(percentile: u32, num_runs: u32) -> usize {
    let as_double = percentile as f64 / 100.0 * (num_runs as f64 - 1.0);
    (as_double.round() as i64).clamp(0, num_runs as i64 - 1) as usize
}

fn pick_percentiles_by_month(
    outputs: &[RunOutput],
    select: impl Fn(&RunOutput) -> &[f64] + Sync,
    percentile_indices: &[usize],
    num_months: usize,
) -> Vec<f64> {
    let per_month: Vec<Vec<f64>> = (0..num_months)
        .into_par_iter()
        .map(|m| {
            let mut vals: Vec<f64> = outputs.iter().map(|o| select(o)[m]).collect();
            vals.sort_by(f64::total_cmp);
            percentile_indices.iter().map(|&i| vals[i]).collect()
        })
        .collect();
    let mut result = vec![0.0; percentile_indices.len() * num_months];
    for (m, vals) in per_month.iter().enumerate() {
        for (pi, &v) in vals.iter().enumerate() {
            result[pi * num_months + m] = v;
        }
    }
    result
}

/// CPU drop-in for `cuda_simulate`.
///
/// # Safety
/// `plan_params`, `plan_params_c_arrays` (including the array pointers inside
/// it, at the lengths implied by num_months / num_percentiles /
/// historical_returns_series_len) and the output array pointers inside `out`
/// (sized num_percentiles * num_months_to_simulate, num_percentiles, and
/// num_months respectively) must all be valid, as for `cuda_simulate`.
pub unsafe fn cpu_simulate(
    num_months_to_simulate: u32,
    current_portfolio_balance: f64,
    plan_params: *const PlanParamsCuda,
    plan_params_c_arrays: *const PlanParamsCuda_C_Arrays,
    out: *mut ResultCudaArrays,
) -> ResultCudaNotArrays {
    let plan_params = &*plan_params;
    let c_arrays = &*plan_params_c_arrays;
    let out = &mut *out;

    let num_months = plan_params.ages.simulation_months.num_months as usize;
    let nms = num_months_to_simulate as usize;
    assert!(nms >= 1 && nms <= num_months);

    // ---- Plan param vectors (port of plan_params_cuda_vectors.cu).
    let future_savings = std::slice::from_raw_parts(c_arrays.future_savings_by_mfn, num_months);
    let income_during_retirement =
        std::slice::from_raw_parts(c_arrays.income_during_retirement_by_mfn, num_months);
    let income_by_mfn: Vec<f64> = future_savings
        .iter()
        .zip(income_during_retirement.iter())
        .map(|(a, b)| a + b)
        .collect();
    let essential_expense_by_mfn: Vec<f64> =
        std::slice::from_raw_parts(c_arrays.essential_expenses_by_mfn, num_months).to_vec();
    let discretionary_expense_by_mfn: Vec<f64> =
        std::slice::from_raw_parts(c_arrays.discretionary_expenses_by_mfn, num_months).to_vec();
    let rra_by_mfn: Vec<f64> =
        std::slice::from_raw_parts(c_arrays.tpaw_rra_including_pos_infinity_by_mfn, num_months)
            .iter()
            .map(|&x| x as f64)
            .collect();
    let spaw_spending_tilt_by_mfn: Vec<f64> =
        std::slice::from_raw_parts(c_arrays.spaw_spending_tilt_by_mfn, num_months)
            .iter()
            .map(|&x| x as f64)
            .collect();
    let stock_allocation_savings_portfolio_by_mfn: Vec<f64> = std::slice::from_raw_parts(
        c_arrays.spaw_and_swr_stock_allocation_savings_portfolio_by_mfn,
        num_months,
    )
    .iter()
    .map(|&x| x as f64)
    .collect();
    let percentiles: Vec<u32> =
        std::slice::from_raw_parts(c_arrays.percentiles, c_arrays.num_percentiles as usize)
            .to_vec();
    let series: Vec<HistoricalReturnsCuda> = std::slice::from_raw_parts(
        c_arrays.historical_returns_series,
        c_arrays.historical_returns_series_len as usize,
    )
    .to_vec();
    let series_len = series.len() as u32;

    // ---- Sampling (port of cuda_process_sampling.cu).
    let sampling = &plan_params.advanced.sampling;
    let (spec, monte_carlo_num_runs) = if sampling.type_
        == PlanParamsCuda_Advanced_Sampling_Type_MonteCarloSampling
    {
        let mc = sampling.monte_carlo_or_historical.monte_carlo;
        (
            SamplingSpec::MonteCarlo {
                seed: mc.seed,
                block_size: mc.block_size,
                stagger_run_starts: mc.stagger_run_starts != 0,
            },
            mc.num_runs,
        )
    } else if sampling.type_ == PlanParamsCuda_Advanced_Sampling_Type_HistoricalSampling {
        (SamplingSpec::Historical, 0)
    } else {
        panic!("Unknown sampling type");
    };
    let num_runs = get_num_runs(&spec, monte_carlo_num_runs, series_len, num_months as u32);

    // ---- Expected returns at month 0.
    let er0_monthly = StocksAndBondsF64 {
        stocks: plan_params
            .advanced
            .return_stats_for_planning
            .expected_returns_at_month_0
            .stocks as f64,
        bonds: plan_params
            .advanced
            .return_stats_for_planning
            .expected_returns_at_month_0
            .bonds as f64,
    };
    let er0 = MonthlyAndAnnual {
        monthly: er0_monthly,
        annual: StocksAndBondsF64 {
            stocks: monthly_to_annual_rate(er0_monthly.stocks),
            bonds: monthly_to_annual_rate(er0_monthly.bonds),
        },
    };

    let strategy = plan_params.advanced.strategy;
    let tpaw_and_spaw = &plan_params.adjustments_to_spending.tpaw_and_spaw;

    // When the series carries no expected-return drift (currently always, as
    // duration matching is not implemented server-side), expected returns are
    // er0 for every (run, month), so the per-(run, month) precomputed entries
    // collapse to one entry per month. This turns the O(num_runs * num_months^2)
    // NPV precompute into O(num_months^2), with bit-identical results.
    let constant_expected_returns = series.iter().all(|h| {
        h.stocks.expected_return_change == 0.0 && h.bonds.expected_return_change == 0.0
    });

    let mut tpaw_net_present_value_exact_month_0_legacy = 0.0;

    let outputs: Vec<RunOutput> = if strategy == PlanParamsCuda_Advanced_Strategy_Strategy_TPAW {
        let (rra_unique, rra_index_by_mfn) = uniquify(&rra_by_mfn);
        let p = TpawParams {
            num_months,
            num_months_to_simulate: nms,
            current_portfolio_balance,
            withdrawal_start_month: plan_params.ages.simulation_months.withdrawal_start_month,
            spending_ceiling: tpaw_and_spaw.spending_ceiling,
            spending_floor: tpaw_and_spaw.spending_floor,
            income_by_mfn: &income_by_mfn,
            essential_expense_by_mfn: &essential_expense_by_mfn,
            discretionary_expense_by_mfn: &discretionary_expense_by_mfn,
            rra_unique: &rra_unique,
            rra_index_by_mfn: &rra_index_by_mfn,
            annual_empirical_log_variance_stocks: plan_params
                .advanced
                .return_stats_for_planning
                .annual_empirical_log_variance_stocks
                as f64,
            time_preference: plan_params.risk.tpaw.time_preference as f64,
            annual_additional_spending_tilt: plan_params
                .risk
                .tpaw
                .annual_additional_spending_tilt as f64,
            legacy_rra_including_pos_infinity: plan_params
                .risk
                .tpaw
                .legacy_rra_including_pos_infinity as f64,
            legacy: tpaw_and_spaw.legacy,
        };

        // Stock allocation report for month 0 (only assigned for TPAW, as in
        // simulate.cu).
        let stock_allocation_by_mfn =
            tpaw_stock_allocation_total_portfolio_for_month_0_by_mfn(&p, &er0);
        let out_alloc = std::slice::from_raw_parts_mut(
            out.tpaw_stock_allocation_total_portfolio_for_month_0_by_mfn,
            num_months,
        );
        for (dst, src) in out_alloc.iter_mut().zip(stock_allocation_by_mfn.iter()) {
            *dst = *src as f32;
        }

        // With no expected-return drift, the entries for every run equal the
        // expected-run entries; compute them once.
        let shared_entries: Option<Vec<tpaw::TpawEntry>> = if constant_expected_returns {
            Some(
                (0..nms)
                    .into_par_iter()
                    .map(|m| tpaw_entry(&p, m, &er0))
                    .collect(),
            )
        } else {
            None
        };

        // Expected run (fills the by-month expected-run data the normal runs
        // scale against).
        let mut expected_data_by_mfn = vec![TpawExpectedRunData::default(); nms];
        {
            let mut balance = current_portfolio_balance;
            for m in 0..nms {
                let entry = match &shared_entries {
                    Some(entries) => entries[m],
                    None => tpaw_entry(&p, m, &er0),
                };
                if m == 0 {
                    tpaw_net_present_value_exact_month_0_legacy = entry.npv_legacy_exact;
                }
                let (result, expected_data) =
                    tpaw_single_month(true, m, balance, &p, &er0.monthly, &entry, None, None);
                expected_data_by_mfn[m] =
                    expected_data.expect("expected run must produce expected data");
                balance = result.balance_ending;
            }
        }

        // Normal runs.
        (0..num_runs)
            .into_par_iter()
            .map(|run_index| {
                let mut path =
                    ReturnsPath::new(&series, make_index_gen(&spec, run_index, series_len), er0_monthly);
                let mut output = RunOutput::new(nms);
                let mut balance = current_portfolio_balance;
                for m in 0..nms {
                    let (historical, expected) = path.next();
                    let entry = match &shared_entries {
                        Some(entries) => entries[m],
                        None => tpaw_entry(&p, m, &expected),
                    };
                    let (result, _) = tpaw_single_month(
                        true,
                        m,
                        balance,
                        &p,
                        &historical,
                        &entry,
                        Some(&expected_data_by_mfn[m]),
                        Some(&mut output),
                    );
                    balance = result.balance_ending;
                }
                output
            })
            .collect()
    } else if strategy == PlanParamsCuda_Advanced_Strategy_Strategy_SPAW {
        let p = SpawParams {
            num_months,
            num_months_to_simulate: nms,
            current_portfolio_balance,
            withdrawal_start_month: plan_params.ages.simulation_months.withdrawal_start_month,
            spending_ceiling: tpaw_and_spaw.spending_ceiling,
            spending_floor: tpaw_and_spaw.spending_floor,
            income_by_mfn: &income_by_mfn,
            essential_expense_by_mfn: &essential_expense_by_mfn,
            discretionary_expense_by_mfn: &discretionary_expense_by_mfn,
            stock_allocation_savings_portfolio_by_mfn: &stock_allocation_savings_portfolio_by_mfn,
            spending_tilt_by_mfn: &spaw_spending_tilt_by_mfn,
            legacy: tpaw_and_spaw.legacy,
        };

        let shared_entries: Option<Vec<spaw::SpawEntry>> = if constant_expected_returns {
            Some(
                (0..nms)
                    .into_par_iter()
                    .map(|m| spaw_entry(&p, m, &er0))
                    .collect(),
            )
        } else {
            None
        };

        let mut expected_data_by_mfn = vec![SpawExpectedRunData::default(); nms];
        {
            let mut balance = current_portfolio_balance;
            for m in 0..nms {
                let entry = match &shared_entries {
                    Some(entries) => entries[m],
                    None => spaw_entry(&p, m, &er0),
                };
                let (result, expected_data) =
                    spaw_single_month(true, m, balance, &p, &er0.monthly, &entry, None, None);
                expected_data_by_mfn[m] =
                    expected_data.expect("expected run must produce expected data");
                balance = result.balance_ending;
            }
        }

        (0..num_runs)
            .into_par_iter()
            .map(|run_index| {
                let mut path =
                    ReturnsPath::new(&series, make_index_gen(&spec, run_index, series_len), er0_monthly);
                let mut output = RunOutput::new(nms);
                let mut balance = current_portfolio_balance;
                for m in 0..nms {
                    let (historical, expected) = path.next();
                    let entry = match &shared_entries {
                        Some(entries) => entries[m],
                        None => spaw_entry(&p, m, &expected),
                    };
                    let (result, _) = spaw_single_month(
                        true,
                        m,
                        balance,
                        &p,
                        &historical,
                        &entry,
                        Some(&expected_data_by_mfn[m]),
                        Some(&mut output),
                    );
                    balance = result.balance_ending;
                }
                output
            })
            .collect()
    } else if strategy == PlanParamsCuda_Advanced_Strategy_Strategy_SWR {
        let p = SwrParams {
            num_months,
            num_months_to_simulate: nms,
            current_portfolio_balance,
            withdrawal_start_month: plan_params.ages.simulation_months.withdrawal_start_month,
            withdrawal_type: plan_params.risk.swr.withdrawal_type,
            withdrawal_as_percent_or_amount: plan_params.risk.swr.withdrawal_as_percent_or_amount,
            income_by_mfn: &income_by_mfn,
            essential_expense_by_mfn: &essential_expense_by_mfn,
            discretionary_expense_by_mfn: &discretionary_expense_by_mfn,
            stock_allocation_savings_portfolio_by_mfn: &stock_allocation_savings_portfolio_by_mfn,
        };

        let shared_entries: Option<Vec<swr::SwrEntry>> = if constant_expected_returns {
            Some(
                (0..nms)
                    .into_par_iter()
                    .map(|m| swr_entry(&p, m, &er0))
                    .collect(),
            )
        } else {
            None
        };

        (0..num_runs)
            .into_par_iter()
            .map(|run_index| {
                let mut path =
                    ReturnsPath::new(&series, make_index_gen(&spec, run_index, series_len), er0_monthly);
                let mut output = RunOutput::new(nms);
                let mut balance = current_portfolio_balance;
                let mut prev_target_withdrawal_general = 0.0;
                for m in 0..nms {
                    let (historical, expected) = path.next();
                    let entry = match &shared_entries {
                        Some(entries) => entries[m],
                        None => swr_entry(&p, m, &expected),
                    };
                    let result = swr_single_month(
                        true,
                        m,
                        balance,
                        prev_target_withdrawal_general,
                        &p,
                        &historical,
                        &entry,
                        Some(&mut output),
                    );
                    balance = result.balance_ending;
                    prev_target_withdrawal_general = result.target_withdrawal_general;
                }
                output
            })
            .collect()
    } else {
        panic!("simulate::unsupported_strategy");
    };

    // ---- Not-arrays result (port of get_result_cuda_not_array.cu).
    let num_runs_with_insufficient_funds = outputs
        .iter()
        .filter(|o| o.num_insufficient_fund_months > 0)
        .count() as u32;

    // ---- Percentiles (ports of sort_run_result_padded.cu +
    // pick_percentiles.cu; no padding needed on CPU).
    let percentile_indices: Vec<usize> = percentiles
        .iter()
        .map(|&p| get_percentile_index(p, num_runs))
        .collect();

    let write_f64 = |ptr: *mut f64, values: &[f64]| {
        std::slice::from_raw_parts_mut(ptr, values.len()).copy_from_slice(values);
    };
    let write_f32 = |ptr: *mut f32, values: &[f64]| {
        let dst = std::slice::from_raw_parts_mut(ptr, values.len());
        for (d, &v) in dst.iter_mut().zip(values.iter()) {
            *d = v as f32;
        }
    };

    write_f64(
        out.by_percentile_by_mfn_simulated_percentile_major_balance_start,
        &pick_percentiles_by_month(&outputs, |o| &o.balance_start, &percentile_indices, nms),
    );
    write_f64(
        out.by_percentile_by_mfn_simulated_percentile_major_withdrawals_essential,
        &pick_percentiles_by_month(
            &outputs,
            |o| &o.withdrawals_essential,
            &percentile_indices,
            nms,
        ),
    );
    write_f64(
        out.by_percentile_by_mfn_simulated_percentile_major_withdrawals_discretionary,
        &pick_percentiles_by_month(
            &outputs,
            |o| &o.withdrawals_discretionary,
            &percentile_indices,
            nms,
        ),
    );
    write_f64(
        out.by_percentile_by_mfn_simulated_percentile_major_withdrawals_general,
        &pick_percentiles_by_month(
            &outputs,
            |o| &o.withdrawals_general,
            &percentile_indices,
            nms,
        ),
    );
    write_f64(
        out.by_percentile_by_mfn_simulated_percentile_major_withdrawals_total,
        &pick_percentiles_by_month(&outputs, |o| &o.withdrawals_total, &percentile_indices, nms),
    );
    write_f32(
        out.by_percentile_by_mfn_simulated_percentile_major_withdrawals_from_savings_portfolio_rate,
        &pick_percentiles_by_month(
            &outputs,
            |o| &o.withdrawals_from_savings_portfolio_rate,
            &percentile_indices,
            nms,
        ),
    );
    write_f32(
        out.by_percentile_by_mfn_simulated_percentile_major_after_withdrawals_allocation_savings_portfolio,
        &pick_percentiles_by_month(
            &outputs,
            |o| &o.after_withdrawals_allocation_savings_portfolio,
            &percentile_indices,
            nms,
        ),
    );
    write_f32(
        out.by_percentile_by_mfn_simulated_percentile_major_after_withdrawals_allocation_total_portfolio_or_zero_if_no_wealth,
        &pick_percentiles_by_month(
            &outputs,
            |o| &o.after_withdrawals_allocation_total_portfolio_or_zero_if_no_wealth,
            &percentile_indices,
            nms,
        ),
    );
    write_f32(
        out.tpaw_by_percentile_by_mfn_simulated_percentile_major_spending_tilt,
        &pick_percentiles_by_month(&outputs, |o| &o.tpaw_spending_tilt, &percentile_indices, nms),
    );

    {
        let mut ending_balances: Vec<f64> = outputs.iter().map(|o| o.ending_balance).collect();
        ending_balances.sort_by(f64::total_cmp);
        let picked: Vec<f64> = percentile_indices
            .iter()
            .map(|&i| ending_balances[i])
            .collect();
        write_f64(out.by_percentile_ending_balance, &picked);
    }

    ResultCudaNotArrays {
        num_runs,
        num_runs_with_insufficient_funds,
        tpaw_net_present_value_exact_month_0_legacy,
    }
}
