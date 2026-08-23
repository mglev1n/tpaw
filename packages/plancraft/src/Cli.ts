#!/usr/bin/env node
import { Command } from 'commander'
import fs from 'fs'
import path from 'path'
import { getYearRows } from './Compile/CompilationReport'
import { CompiledScenario, compileScenario } from './Compile/CompileToPlanParams'
import { resolveScenario, ScenarioError } from './Compile/ResolveScenario'
import { getScenarioJsonSchema } from './Schema/GenJsonSchema'
import {
  DEFAULT_SIMULATOR_URL,
  simulate,
  SimulationOutcome,
} from './Engine/SimulateClient'
import { writeOutputBundle } from './Emit/OutputBundle'

const program = new Command()

const _fmtUsd = (x: number) =>
  '$' + x.toLocaleString('en-US', { maximumFractionDigits: 0 })

const _loadAndCompile = (scenarioPath: string): CompiledScenario => {
  const resolved = resolveScenario(
    path.resolve(scenarioPath),
    (p) => fs.readFileSync(p, 'utf8'),
    (fromFile, relative) => path.resolve(path.dirname(fromFile), relative),
  )
  return compileScenario(resolved)
}

const _handleError = (e: unknown): never => {
  if (e instanceof ScenarioError) {
    console.error(`\nScenario error:\n${e.message}`)
    process.exit(1)
  }
  throw e
}

const _printOutcomeSummary = (
  compiled: CompiledScenario,
  outcome: SimulationOutcome,
) => {
  console.log(`  Runs: ${outcome.numRuns}`)
  console.log(
    `  Success probability: ${(outcome.successProbability * 100).toFixed(1)}% ` +
      `(${outcome.numRunsWithInsufficientFunds} runs ran out of money)`,
  )
  const median = outcome.balanceStart.find((x) => x.percentile === 50)
  if (median) {
    const at = (mfn: number) => _fmtUsd(median.data[Math.min(mfn, median.data.length - 1)] ?? 0)
    console.log(
      `  Median balance: now ${at(0)} | at retirement (month ` +
        `${compiled.withdrawalStartMFN}) ${at(compiled.withdrawalStartMFN)}`,
    )
  }
  for (const { percentile, balance } of outcome.endingBalanceByPercentile)
    console.log(`  Ending balance p${percentile}: ${_fmtUsd(balance)}`)
}

program
  .name('plancraft')
  .description(
    'Compile LLM-friendly scenario JSON to TPAW Planner plans, simulate, and compare.',
  )

program
  .command('compile')
  .description(
    'Compile scenario files to PlanParams, a .tpaw.txt plan file (openable ' +
      'at tpawplanner.com/plan), and a compilation report.',
  )
  .argument('<scenarios...>', 'scenario JSON files')
  .option('-o, --out <dir>', 'output directory', 'out')
  .action((scenarioPaths: string[], opts: { out: string }) => {
    try {
      for (const scenarioPath of scenarioPaths) {
        const compiled = _loadAndCompile(scenarioPath)
        const { dir } = writeOutputBundle(opts.out, compiled, null)
        console.log(`${compiled.scenario.meta.name} -> ${dir}`)
        const rows = getYearRows(compiled).filter((r) => r.netFlow !== 0)
        if (rows.length > 0) {
          const first = rows[0]!
          const last = rows[rows.length - 1]!
          console.log(
            `  Cash-flow years ${first.calendarYear}-${last.calendarYear}, ` +
              `first-year net flow ${_fmtUsd(first.netFlow)}`,
          )
        }
      }
    } catch (e) {
      _handleError(e)
    }
  })

program
  .command('simulate')
  .description('Compile and simulate scenario files against a simulator endpoint.')
  .argument('<scenarios...>', 'scenario JSON files')
  .option('-o, --out <dir>', 'output directory', 'out')
  .option('-u, --url <url>', 'simulator base URL', DEFAULT_SIMULATOR_URL)
  .option('--runs <n>', 'override number of Monte Carlo runs')
  .option('--seed <n>', 'override random seed')
  .action(
    async (
      scenarioPaths: string[],
      opts: { out: string; url: string; runs?: string; seed?: string },
    ) => {
      try {
        for (const scenarioPath of scenarioPaths) {
          const compiled = _loadAndCompile(scenarioPath)
          if (opts.runs !== undefined)
            compiled.simulationArgs.numRuns = parseInt(opts.runs, 10)
          if (opts.seed !== undefined)
            compiled.simulationArgs.seed = parseInt(opts.seed, 10)
          console.log(`${compiled.scenario.meta.name}: simulating...`)
          const outcome = await simulate(compiled, { url: opts.url })
          const { dir } = writeOutputBundle(opts.out, compiled, outcome)
          _printOutcomeSummary(compiled, outcome)
          console.log(`  Outputs: ${dir}`)
        }
      } catch (e) {
        _handleError(e)
      }
    },
  )

program
  .command('schema')
  .description('Print the scenario JSON Schema (for LLM prompt context).')
  .action(() => {
    console.log(JSON.stringify(getScenarioJsonSchema(), null, 2))
  })

program.parseAsync().catch((e) => {
  console.error(e)
  process.exit(1)
})
