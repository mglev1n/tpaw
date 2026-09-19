# @tpaw/plancraft

A scenario layer for [TPAW Planner](https://tpawplanner.com): describe a
household's financial trajectory — income phases, expenses, one-time
purchases, retirement decisions — as **LLM-friendly JSON**, compile it to a
standard TPAW plan, simulate it against the TPAW simulator, and compare
scenarios side by side.

- Scenario format guide: [`docs/SCENARIO_FORMAT.md`](docs/SCENARIO_FORMAT.md)
- Machine-readable schema: [`docs/scenario.schema.json`](docs/scenario.schema.json)
  (give both to an LLM along with a financial plan document to generate
  scenarios)

## Setup

```bash
cd packages/common && npm install && npm run build
cd ../plancraft && npm install && npm run build
```

## Usage

```bash
# Compile: PlanParams JSON + .tpaw.txt plan file (openable at
# tpawplanner.com/plan) + a compilation report of the derived cash flows.
node dist/Cli.js compile examples/base.scenario.json --out out

# Simulate against the hosted simulator (default
# https://simulator.tpawplanner.com), writing result.json and a tidy
# trajectories.csv for analysis in R/Python.
node dist/Cli.js simulate examples/base.scenario.json --out out

# Compare scenarios: one self-contained HTML report.
node dist/Cli.js compare examples/household/*.scenario.json \
  --base examples/household/base.scenario.json --out report.html

# Run a decision grid: a static report plus an interactive explorer that
# filters by decision, re-ranks by metric, and drills into any single
# combination's trajectory.
node dist/Cli.js grid examples/household/grid-retirement/grid.json \
  --out grid-report.html --explorer explorer.html --csv grid.csv

# Print the scenario JSON Schema.
node dist/Cli.js schema
```

`compare` caches simulation results by request content in
`.plancraft-cache/`, so re-rendering a report does not re-hit the simulator.

## Design notes

- **Net-contributions abstraction.** The engine models one portfolio;
  scenarios express decisions as savings/expense/income events in real,
  after-tax dollars. Taxes are deliberately out of scope — compute net
  amounts upstream (by hand or via the LLM generating the scenario).
- **Validation by construction.** Every compiled scenario passes
  `planParamsGuard` and the normalization round-trip from `@tpaw/common` —
  if plancraft accepts it, the real planner accepts it.
- **`src/Engine/{GetPlanParamsServer,DeWire}.ts` and `src/Engine/Wire/` are
  verbatim copies** of `packages/web/src/Simulator/SimulateOnServer/*`,
  guarded by `UpstreamDrift.test.ts`. If that test fails after pulling
  upstream changes, re-copy the files (commands in the test header).
- **Wire protocol version.** The client speaks `/3/simulate`. If the hosted
  simulator moves on, it responds `clientNeedsUpdate`; sync the protos in
  `packages/simulator-rust/src/lib/wire` from upstream and regenerate
  (`npm run gen-wire`), or run a local simulator (below).

## Local simulator (no hosted API needed)

`packages/simulator-rust` includes a pure-Rust CPU port of the CUDA engine
(`src/lib/sim_cpu/`), so the simulator server can run locally with no GPU,
no cloud credentials, and no network:

```bash
cd packages/simulator-rust
cargo build --release          # needs protobuf-compiler (protoc) installed
PORT=8123 ./target/release/simulator serve
# then point plancraft at it:
node dist/Cli.js simulate examples/base.scenario.json -u http://127.0.0.1:8123
```

With no `MARKET_DATA_BUCKET` configured the server uses synthetic market
data — fine for plancraft scenarios, which pin fixed expected returns and
manual inflation (market-data-derived *presets* like "suggested inflation"
would not reflect real data). Monte Carlo draws are bit-exact with the GPU
backend (same cuRAND XORWOW sequences); floating point results agree with
the hosted simulator to within f32 precision (observed ≤ 0.003% on
household scenarios, since the CPU port computes in f64 while the GPU runs
f32 "efficient mode"). ~200ms per 2,000-run simulation on a 4-core machine.
