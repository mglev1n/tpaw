// Bit-exact CPU implementation of cuRAND's XORWOW generator
// (curandStateXORWOW_t), including curand_init()'s per-subsequence skip-ahead
// of 2^67 steps, so that Monte Carlo index sequences match the CUDA backend
// exactly for a given (seed, run_index).

use once_cell::sync::Lazy;

const WORDS: usize = 5;
const BITS: usize = WORDS * 32; // 160-bit xorshift state (the Weyl counter d is not part of the linear state).

#[derive(Clone, Copy)]
pub struct Xorwow {
    v: [u32; WORDS],
    d: u32,
}

impl Xorwow {
    // Equivalent to curand_init(seed, subsequence, 0, &state).
    pub fn new(seed: u64, subsequence: u64) -> Self {
        let s0 = (seed as u32) ^ 0xaad26b49;
        let s1 = ((seed >> 32) as u32) ^ 0xf7dcefdd;
        let t0 = 1099087573u32.wrapping_mul(s0);
        let t1 = 2591861531u32.wrapping_mul(s1);
        let mut state = Xorwow {
            v: [
                123456789u32.wrapping_add(t0),
                362436069u32 ^ t0,
                521288629u32.wrapping_add(t1),
                88675123u32 ^ t1,
                5783321u32.wrapping_add(t0),
            ],
            d: 6615241u32.wrapping_add(t1).wrapping_add(t0),
        };
        // Each subsequence is 2^67 steps ahead. The Weyl counter advances by
        // 362437 * 2^67 mod 2^32 = 0 per subsequence, so only v changes.
        state.v = skip_subsequences(&state.v, subsequence);
        state
    }

    // Equivalent to curand(&state).
    pub fn next_u32(&mut self) -> u32 {
        let t = self.v[0] ^ (self.v[0] >> 2);
        self.v[0] = self.v[1];
        self.v[1] = self.v[2];
        self.v[2] = self.v[3];
        self.v[3] = self.v[4];
        self.v[4] = (self.v[4] ^ (self.v[4] << 4)) ^ (t ^ (t << 1));
        self.d = self.d.wrapping_add(362437);
        self.v[4].wrapping_add(self.d)
    }

    // Equivalent to get_random_index() in
    // packages/simulator-cuda/src/device_utils/get_random_index.cu (rejection
    // sampling for an unbiased index).
    pub fn get_random_index(&mut self, array_size: u32) -> u32 {
        let limit = u32::MAX - (u32::MAX % array_size);
        let mut x = self.next_u32();
        while x >= limit {
            x = self.next_u32();
        }
        x % array_size
    }
}

// The v-part of one XORWOW step, as a linear map over GF(2).
fn step_v(v: &[u32; WORDS]) -> [u32; WORDS] {
    let t = v[0] ^ (v[0] >> 2);
    [v[1], v[2], v[3], v[4], (v[4] ^ (v[4] << 4)) ^ (t ^ (t << 1))]
}

// 160x160 GF(2) matrix stored as columns: apply(M, v) = XOR of columns at v's
// set bits.
#[derive(Clone)]
struct BitMatrix {
    cols: Vec<[u32; WORDS]>, // len BITS
}

impl BitMatrix {
    fn from_fn(f: impl Fn(&[u32; WORDS]) -> [u32; WORDS]) -> Self {
        let mut cols = vec![[0u32; WORDS]; BITS];
        for (j, col) in cols.iter_mut().enumerate() {
            let mut e = [0u32; WORDS];
            e[j / 32] = 1u32 << (j % 32);
            *col = f(&e);
        }
        BitMatrix { cols }
    }

    fn apply(&self, v: &[u32; WORDS]) -> [u32; WORDS] {
        let mut out = [0u32; WORDS];
        for (j, col) in self.cols.iter().enumerate() {
            if (v[j / 32] >> (j % 32)) & 1 == 1 {
                for w in 0..WORDS {
                    out[w] ^= col[w];
                }
            }
        }
        out
    }

    fn mul(&self, other: &BitMatrix) -> BitMatrix {
        BitMatrix {
            cols: other.cols.iter().map(|c| self.apply(c)).collect(),
        }
    }

    fn square(&self) -> BitMatrix {
        self.mul(self)
    }
}

// SKIP_MATRICES[k] = M^(2^67 * 2^k) where M is the one-step matrix, i.e. the
// matrix that advances by 2^k subsequences.
static SKIP_MATRICES: Lazy<Vec<BitMatrix>> = Lazy::new(|| {
    let mut m = BitMatrix::from_fn(step_v);
    for _ in 0..67 {
        m = m.square();
    }
    let mut result = Vec::with_capacity(64);
    for _ in 0..64 {
        let next = m.square();
        result.push(m);
        m = next;
    }
    result
});

fn skip_subsequences(v: &[u32; WORDS], subsequence: u64) -> [u32; WORDS] {
    let mut v = *v;
    let mut n = subsequence;
    let mut k = 0;
    while n != 0 {
        if n & 1 == 1 {
            v = SKIP_MATRICES[k].apply(&v);
        }
        n >>= 1;
        k += 1;
    }
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    // Reference: skipping via explicit stepping must match the matrix skip.
    // (2^67 steps is infeasible; instead check the matrix algebra itself: the
    // one-step matrix applied n times equals n explicit steps.)
    #[test]
    fn matrix_matches_stepping() {
        let m = BitMatrix::from_fn(step_v);
        let state = Xorwow::new(42, 0);
        let mut v_expect = state.v;
        let mut v_matrix = state.v;
        for _ in 0..123 {
            v_expect = step_v(&v_expect);
            v_matrix = m.apply(&v_matrix);
        }
        assert_eq!(v_expect, v_matrix);
    }

    #[test]
    fn matrix_power_composition() {
        // M^(2^67 * 3) == M^(2^67) applied 3 times.
        let m1 = &SKIP_MATRICES[0];
        let state = Xorwow::new(7, 0);
        let direct = skip_subsequences(&state.v, 3);
        let mut via_single = state.v;
        for _ in 0..3 {
            via_single = m1.apply(&via_single);
        }
        assert_eq!(direct, via_single);
    }
}
