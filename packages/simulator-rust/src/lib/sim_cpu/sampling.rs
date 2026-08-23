// CPU port of packages/simulator-cuda/src/simulate/cuda_process_sampling.cu.
// Generates, per run, the sequence of indices into the historical returns
// series. Bit-exact with the CUDA backend for Monte Carlo sampling.

use super::xorwow::Xorwow;

#[derive(Clone, Copy, Debug)]
pub enum SamplingSpec {
    MonteCarlo {
        seed: u64,
        block_size: u32,
        stagger_run_starts: bool,
    },
    Historical,
}

pub struct MonteCarloIndexGen {
    rng: Xorwow,
    len: u32,
    block_size: u32,
    next_index: u32,
    last_value: u32,
}

impl MonteCarloIndexGen {
    pub fn new(
        seed: u64,
        run_index: u32,
        block_size: u32,
        len: u32,
        stagger_run_starts: bool,
    ) -> Self {
        let mut gen = MonteCarloIndexGen {
            rng: Xorwow::new(seed, run_index as u64),
            len,
            block_size,
            next_index: 0,
            last_value: 0,
        };
        let stagger = if stagger_run_starts {
            run_index % block_size
        } else {
            0
        };
        for _ in 0..stagger {
            gen.next();
        }
        gen
    }

    pub fn next(&mut self) -> u32 {
        self.last_value = if self.next_index % self.block_size == 0 {
            self.rng.get_random_index(self.len)
        } else {
            (self.last_value + 1) % self.len
        };
        self.next_index += 1;
        self.last_value
    }
}

pub enum IndexGen {
    MonteCarlo(MonteCarloIndexGen),
    Historical { run_index: u32, month_index: u32 },
}

impl IndexGen {
    pub fn next(&mut self) -> u32 {
        match self {
            IndexGen::MonteCarlo(gen) => gen.next(),
            IndexGen::Historical {
                run_index,
                month_index,
            } => {
                let result = *run_index + *month_index;
                *month_index += 1;
                result
            }
        }
    }
}

pub fn get_num_runs(
    spec: &SamplingSpec,
    monte_carlo_num_runs: u32,
    historical_returns_series_len: u32,
    num_months: u32,
) -> u32 {
    match spec {
        SamplingSpec::MonteCarlo { .. } => monte_carlo_num_runs,
        SamplingSpec::Historical => historical_returns_series_len - (num_months - 1),
    }
}

pub fn make_index_gen(spec: &SamplingSpec, run_index: u32, series_len: u32) -> IndexGen {
    match spec {
        SamplingSpec::MonteCarlo {
            seed,
            block_size,
            stagger_run_starts,
        } => IndexGen::MonteCarlo(MonteCarloIndexGen::new(
            *seed,
            run_index,
            *block_size,
            series_len,
            *stagger_run_starts,
        )),
        SamplingSpec::Historical => IndexGen::Historical {
            run_index,
            month_index: 0,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Truth tables from cuda_process_sampling.cu TEST_CASE("monte_carlo"):
    // seed=1234, num_runs=4, block_size=3, series len 1000, 10 months.
    const TRUTH_NO_STAGGER: [[u32; 10]; 4] = [
        [773, 774, 775, 844, 845, 846, 282, 283, 284, 316],
        [202, 203, 204, 785, 786, 787, 705, 706, 707, 676],
        [744, 745, 746, 504, 505, 506, 60, 61, 62, 224],
        [439, 440, 441, 58, 59, 60, 990, 991, 992, 836],
    ];
    const TRUTH_STAGGER: [[u32; 10]; 4] = [
        [773, 774, 775, 844, 845, 846, 282, 283, 284, 316],
        [203, 204, 785, 786, 787, 705, 706, 707, 676, 677],
        [746, 504, 505, 506, 60, 61, 62, 224, 225, 226],
        [439, 440, 441, 58, 59, 60, 990, 991, 992, 836],
    ];

    fn generate(stagger: bool) -> Vec<Vec<u32>> {
        (0..4u32)
            .map(|run| {
                let mut gen = MonteCarloIndexGen::new(1234, run, 3, 1000, stagger);
                (0..10).map(|_| gen.next()).collect()
            })
            .collect()
    }

    #[test]
    fn monte_carlo_matches_cuda_truth_table_no_stagger() {
        let result = generate(false);
        for (run, truth) in TRUTH_NO_STAGGER.iter().enumerate() {
            assert_eq!(result[run], truth.to_vec(), "run {}", run);
        }
    }

    #[test]
    fn monte_carlo_matches_cuda_truth_table_stagger() {
        let result = generate(true);
        for (run, truth) in TRUTH_STAGGER.iter().enumerate() {
            assert_eq!(result[run], truth.to_vec(), "run {}", run);
        }
    }

    #[test]
    fn historical_indices() {
        // From TEST_CASE("_historical"): num_months=5, series len 6 -> 2 runs,
        // index = run + month.
        let mut gen0 = make_index_gen(&SamplingSpec::Historical, 0, 6);
        let mut gen1 = make_index_gen(&SamplingSpec::Historical, 1, 6);
        assert_eq!((gen0.next(), gen0.next()), (0, 1));
        assert_eq!((gen1.next(), gen1.next()), (1, 2));
        assert_eq!(get_num_runs(&SamplingSpec::Historical, 0, 6, 5), 2);
    }
}
