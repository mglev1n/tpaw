import { PlanParamsNormalized, assert, block, fGet, noCase } from '@tpaw/common'
import { CompiledScenario } from '../Compile/CompileToPlanParams'
import { deWire } from './DeWire'
import { getPlanParamsServer } from './GetPlanParamsServer'
import {
  WireSimulationArgs,
  WireSimulationResult,
} from './Wire/wire_simulate_api'

export const DEFAULT_SIMULATOR_URL = 'https://simulator.tpawplanner.com'
const WIRE_VERSION = 3
const MAX_RETRIES = 5
const TIMEOUT_MS = 30000

export type DailyMarketSeriesSrc =
  | { type: 'live' }
  | { type: 'syntheticLiveRepeated' }
  | {
      type: 'syntheticConstant'
      annualPercentageChangeVT: number
      annualPercentageChangeBND: number
    }

export type PercentileTrajectory = { percentile: number; data: number[] }

export type SimulationOutcome = {
  numRuns: number
  numRunsWithInsufficientFunds: number
  successProbability: number
  percentiles: number[]
  numMonths: number
  // Each series is by-percentile, each entry a by-months-from-now array.
  balanceStart: PercentileTrajectory[]
  withdrawalsEssential: PercentileTrajectory[]
  withdrawalsDiscretionary: PercentileTrajectory[]
  withdrawalsRegular: PercentileTrajectory[]
  withdrawalsTotal: PercentileTrajectory[]
  stockAllocationSavingsPortfolio: PercentileTrajectory[]
  endingBalanceByPercentile: { percentile: number; balance: number }[]
  serverPerformance: unknown
}

export const getWireSimulationArgs = (compiled: CompiledScenario): WireSimulationArgs => {
  const { norm, planParams, simulationArgs } = compiled
  assert(planParams.wealth.portfolioBalance.isDatedPlan === false)
  return {
    currentPortfolioBalance: {
      $case: 'noEstimate',
      noEstimate: planParams.wealth.portfolioBalance.amount,
    },
    marketDailySeriesSrc: { $case: 'live', live: {} },
    percentiles: simulationArgs.percentiles,
    timestampForMarketDataMs: norm.datingInfo.timestampForMarketData,
    planParams: getPlanParamsServer(
      norm,
      simulationArgs.numRuns,
      simulationArgs.seed,
    ),
  }
}

export class SimulatorProtocolError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'SimulatorProtocolError'
  }
}

export const simulate = async (
  compiled: CompiledScenario,
  opts: { url?: string } = {},
): Promise<SimulationOutcome> => {
  const wireArgs = getWireSimulationArgs(compiled)
  const baseUrl = (opts.url ?? DEFAULT_SIMULATOR_URL).replace(/\/+$/, '')
  const url = `${baseUrl}/${WIRE_VERSION}/simulate`
  const body = WireSimulationArgs.encode(wireArgs).finish()

  let lastError: string | null = null
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    if (attempt > 0)
      await new Promise((resolve) => setTimeout(resolve, 500 * attempt))
    let response: Response
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        // Copy into a fresh ArrayBuffer-backed view for fetch's BodyInit type.
        body: Uint8Array.from(body),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      })
    } catch (e) {
      lastError = `network error: ${e instanceof Error ? e.message : String(e)}`
      continue
    }
    if (response.status >= 500) {
      lastError = `server error: HTTP ${response.status}`
      continue
    }
    if (response.headers.get('x-app-error-code') === 'clientNeedsUpdate')
      throw new SimulatorProtocolError(
        'The simulator at ' +
          baseUrl +
          ' no longer speaks wire version ' +
          `${WIRE_VERSION} (clientNeedsUpdate). The wire protos in this repo ` +
          'have drifted from the server: sync packages/simulator-rust/src/lib/wire ' +
          'from upstream and regenerate (npm run gen-wire), or run a local ' +
          'simulator built from this repo.',
      )
    if (!response.ok)
      throw new SimulatorProtocolError(
        `Simulator returned HTTP ${response.status}: ${await response.text()}`,
      )
    const data = new Uint8Array(await response.arrayBuffer())
    return _processResult(
      WireSimulationResult.decode(data),
      compiled.norm,
      compiled.simulationArgs.percentiles,
    )
  }
  throw new SimulatorProtocolError(
    `Simulation failed after ${MAX_RETRIES} attempts (${lastError ?? 'unknown'}).`,
  )
}

const _processResult = (
  wireIn: WireSimulationResult,
  norm: PlanParamsNormalized,
  percentiles: number[],
): SimulationOutcome => {
  const autoDeWired = deWire(wireIn)
  const numMonths = norm.ages.simulationMonths.numMonths
  const arrays = autoDeWired.arrays

  const byPercentileByMFN = (
    percentileMajor: number[],
  ): PercentileTrajectory[] => {
    assert(percentileMajor.length === numMonths * percentiles.length)
    return percentiles.map((percentile, i) => ({
      percentile,
      data: percentileMajor.slice(i * numMonths, (i + 1) * numMonths),
    }))
  }

  const numRuns = autoDeWired.numRuns
  const numRunsWithInsufficientFunds = autoDeWired.numRunsWithInsufficientFunds
  return {
    numRuns,
    numRunsWithInsufficientFunds,
    successProbability: (numRuns - numRunsWithInsufficientFunds) / numRuns,
    percentiles,
    numMonths,
    balanceStart: byPercentileByMFN(
      arrays.byPercentileByMfnSimulatedPercentileMajorBalanceStart,
    ),
    withdrawalsEssential: byPercentileByMFN(
      arrays.byPercentileByMfnSimulatedPercentileMajorWithdrawalsEssential,
    ),
    withdrawalsDiscretionary: byPercentileByMFN(
      arrays.byPercentileByMfnSimulatedPercentileMajorWithdrawalsDiscretionary,
    ),
    withdrawalsRegular: byPercentileByMFN(
      arrays.byPercentileByMfnSimulatedPercentileMajorWithdrawalsGeneral,
    ),
    withdrawalsTotal: byPercentileByMFN(
      arrays.byPercentileByMfnSimulatedPercentileMajorWithdrawalsTotal,
    ),
    stockAllocationSavingsPortfolio: byPercentileByMFN(
      arrays.byPercentileByMfnSimulatedPercentileMajorAfterWithdrawalsAllocationSavingsPortfolio,
    ),
    endingBalanceByPercentile: block(() => {
      const byPercentile = arrays.byPercentileEndingBalance
      assert(byPercentile.length === percentiles.length)
      return percentiles.map((percentile, i) => ({
        percentile,
        balance: fGet(byPercentile[i]),
      }))
    }),
    serverPerformance: autoDeWired.performance,
  }
}
