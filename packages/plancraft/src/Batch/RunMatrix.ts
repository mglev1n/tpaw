import crypto from 'crypto'
import fs from 'fs'
import path from 'path'
import { CompiledScenario, compileScenario } from '../Compile/CompileToPlanParams'
import { resolveScenario } from '../Compile/ResolveScenario'
import {
  getWireSimulationArgs,
  simulate,
  SimulationOutcome,
} from '../Engine/SimulateClient'
import { WireSimulationArgs } from '../Engine/Wire/wire_simulate_api'

export type ScenarioRun = {
  scenarioPath: string
  compiled: CompiledScenario
  outcome: SimulationOutcome
  fromCache: boolean
}

// "Now" truncated to UTC midnight: keeps compiled params (and therefore the
// simulation request bytes and the result cache key) stable across runs on
// the same day.
export const startOfTodayUtc = (): number => {
  const d = new Date()
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
}

export const loadAndCompileScenario = (scenarioPath: string): CompiledScenario =>
  compileScenario(
    resolveScenario(
      path.resolve(scenarioPath),
      (p) => fs.readFileSync(p, 'utf8'),
      (fromFile, relative) => path.resolve(path.dirname(fromFile), relative),
    ),
    { now: startOfTodayUtc() },
  )

// Content-addressed cache: the key is the exact simulation request (wire
// bytes) plus the endpoint, so identical requests never re-hit the service
// and re-reports are instant. timestampForMarketDataMs is part of the wire
// bytes, so plans without a pinned meta.marketDataDate naturally miss the
// cache on a new day.
const _cacheKey = (wireArgs: WireSimulationArgs, url: string): string =>
  crypto
    .createHash('sha256')
    .update(url)
    .update(WireSimulationArgs.encode(wireArgs).finish())
    .digest('hex')

export const runScenarios = async (
  scenarioPaths: string[],
  opts: {
    url?: string
    cacheDir?: string
    concurrency?: number
    onProgress?: (message: string) => void
  } = {},
): Promise<ScenarioRun[]> => {
  const concurrency = opts.concurrency ?? 2
  const onProgress = opts.onProgress ?? (() => {})
  const jobs = scenarioPaths.map((scenarioPath) => ({
    scenarioPath,
    compiled: loadAndCompileScenario(scenarioPath),
  }))

  const results: ScenarioRun[] = new Array(jobs.length)
  let next = 0
  const worker = async () => {
    while (next < jobs.length) {
      const index = next++
      const { scenarioPath, compiled } = jobs[index]!
      const name = compiled.scenario.meta.name

      let cachePath: string | null = null
      if (opts.cacheDir) {
        const key = _cacheKey(
          getWireSimulationArgs(compiled),
          opts.url ?? 'default',
        )
        cachePath = path.join(opts.cacheDir, `${key}.json`)
        if (fs.existsSync(cachePath)) {
          onProgress(`${name}: cached`)
          results[index] = {
            scenarioPath,
            compiled,
            outcome: JSON.parse(
              fs.readFileSync(cachePath, 'utf8'),
            ) as SimulationOutcome,
            fromCache: true,
          }
          continue
        }
      }
      onProgress(`${name}: simulating...`)
      const outcome = await simulate(compiled, { url: opts.url })
      if (cachePath) {
        fs.mkdirSync(path.dirname(cachePath), { recursive: true })
        fs.writeFileSync(cachePath, JSON.stringify(outcome))
      }
      results[index] = { scenarioPath, compiled, outcome, fromCache: false }
    }
  }
  await Promise.all(
    new Array(Math.min(concurrency, jobs.length)).fill(null).map(worker),
  )
  return results
}
