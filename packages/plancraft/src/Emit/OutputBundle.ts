import fs from 'fs'
import path from 'path'
import { CompiledScenario } from '../Compile/CompileToPlanParams'
import { getCompilationReport } from '../Compile/CompilationReport'
import { SimulationOutcome, PercentileTrajectory } from '../Engine/SimulateClient'
import { getPlanFileContent, PLAN_FILE_EXTENSION } from './PlanFile'

export const scenarioSlug = (name: string): string =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'scenario'

// Tidy long-format CSV of the simulated trajectories, for analysis in
// R/Python: series,percentile,mfn,calendarYear,person1Age,value
export const getTrajectoriesCsv = (
  compiled: CompiledScenario,
  outcome: SimulationOutcome,
): string => {
  const rows: string[] = ['series,percentile,mfn,calendarYear,person1Age,value']
  const push = (series: string, trajectories: PercentileTrajectory[]) => {
    for (const t of trajectories) {
      t.data.forEach((value, mfn) => {
        const calendarYear =
          compiled.anchor.year + Math.floor((compiled.anchor.month - 1 + mfn) / 12)
        const person1Age = Math.floor(
          (compiled.ages.person1.currentAgeMonths + mfn) / 12,
        )
        rows.push(
          `${series},${t.percentile},${mfn},${calendarYear},${person1Age},${value}`,
        )
      })
    }
  }
  push('balance', outcome.balanceStart)
  push('withdrawalsEssential', outcome.withdrawalsEssential)
  push('withdrawalsDiscretionary', outcome.withdrawalsDiscretionary)
  push('withdrawalsRegular', outcome.withdrawalsRegular)
  push('withdrawalsTotal', outcome.withdrawalsTotal)
  push('stockAllocation', outcome.stockAllocationSavingsPortfolio)
  return rows.join('\n') + '\n'
}

export const writeOutputBundle = (
  outDir: string,
  compiled: CompiledScenario,
  outcome: SimulationOutcome | null,
): { dir: string; files: string[] } => {
  const slug = scenarioSlug(compiled.scenario.meta.name)
  const dir = path.join(outDir, slug)
  fs.mkdirSync(dir, { recursive: true })
  const files: string[] = []
  const write = (name: string, content: string) => {
    fs.writeFileSync(path.join(dir, name), content)
    files.push(path.join(dir, name))
  }
  write('plan.json', JSON.stringify(compiled.planParams, null, 2) + '\n')
  write(`${slug}${PLAN_FILE_EXTENSION}`, getPlanFileContent(compiled.planParams))
  write('compilation-report.md', getCompilationReport(compiled))
  if (outcome) {
    const { balanceStart, withdrawalsEssential, withdrawalsDiscretionary,
      withdrawalsRegular, withdrawalsTotal, stockAllocationSavingsPortfolio,
      ...summary } = outcome
    write('result.json', JSON.stringify(summary, null, 2) + '\n')
    write('trajectories.csv', getTrajectoriesCsv(compiled, outcome))
  }
  return { dir, files }
}
