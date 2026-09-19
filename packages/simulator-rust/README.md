# simulator

The TPAW simulation server (axum, `POST /3/simulate`, protobuf wire format).

## Backends

- **CPU (default).** `cargo build` with no features uses the pure-Rust port
  of the CUDA engine in `src/lib/sim_cpu/`. No GPU, no CUDA toolkit, and no
  cloud credentials required. Monte Carlo index sequences are bit-exact with
  the CUDA backend (cuRAND XORWOW, including the 2^67-step per-subsequence
  skip-ahead, verified against the truth tables in
  `packages/simulator-cuda/src/simulate/cuda_process_sampling.cu`). Floating
  point math runs in f64 (the CUDA codebase's "REPLICATION MODE" numerics),
  so results differ from the f32 "EFFICIENT MODE" GPU backend only at the
  f32-precision level.
- **CUDA.** `cargo build --features cuda` links `libsimulator-cuda` (built
  from `packages/simulator-cuda` with nvcc) plus the CUDA runtime, and
  routes `simulate()` through `cuda_simulate`.

## Running locally

```bash
# protoc is required by the build (prost); e.g. apt-get install protobuf-compiler
cargo build --release
PORT=8123 ./target/release/simulator serve
```

All environment variables have local-friendly defaults (see
`src/lib/config.rs`). Market data source, in order of precedence:

1. `MARKET_DATA_LOCAL_DIR` — directory containing
   `daily_market_data_for_presets.json` and `vt_and_bnd.json` (the same JSON
   format stored in GCS).
2. `MARKET_DATA_BUCKET` — download from GCS (production behavior; needs
   `GCP_KEY_PATH`).
3. Neither set — a synthetic constant series. Fine for clients that pin
   fixed expected returns and manual inflation (e.g. `packages/plancraft`);
   market-data-derived presets will not reflect real data.

## Historical build notes

wasm build: `wasm-pack build --out-dir ../simulator --scope tpaw`

Regenerating the CUDA bindings (`src/lib/cuda_bridge.rs`) — remove the
`extern "C"` from the header first:
`~/.cargo/bin/bindgen src/cuda/cuda.h -o src/bindings.rs`
