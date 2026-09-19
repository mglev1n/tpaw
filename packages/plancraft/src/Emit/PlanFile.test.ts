import { scenarioFileSchema } from '../Schema/ScenarioSchema'
import { compileScenario } from '../Compile/CompileToPlanParams'
import { getPlanFileContent, parsePlanFileContent } from './PlanFile'

const NOW = 1755950400000

const scenario = scenarioFileSchema.parse({
  plancraft: 1,
  meta: { name: 'Plan file test', anchorYear: 2026 },
  household: {
    person1: { currentAge: { years: 40 }, retirementAge: { years: 65 } },
  },
  portfolio: { balance: 250000 },
  events: [
    {
      id: 'save',
      kind: 'savings',
      amount: { perMonth: 4000 },
      timing: { from: { named: 'now' }, to: { named: 'lastWorkingMonth' } },
    },
  ],
})

describe('plan file emitter', () => {
  test('generates a .tpaw.txt that re-parses to the same params', () => {
    const compiled = compileScenario(scenario, { now: NOW })
    const content = getPlanFileContent(compiled.planParams)
    expect(content).toContain('---- PLAN DATA STARTS HERE ----')
    const reParsed = parsePlanFileContent(content)
    expect(reParsed).toEqual(compiled.planParams)
  })

  test('rejects corrupted content', () => {
    expect(parsePlanFileContent('no json here')).toBeNull()
    expect(parsePlanFileContent('{"v":1,"planParamsHistory":[]}')).toBeNull()
  })
})
