import fs from 'fs'
import path from 'path'
import { zodToJsonSchema } from 'zod-to-json-schema'
import { scenarioFileSchema, eventFragmentFileSchema } from './ScenarioSchema'

export const getScenarioJsonSchema = (): Record<string, unknown> =>
  // Cast: zod 3.25's deep generic types trip TS2589 in zodToJsonSchema's
  // signature; runtime behavior is unaffected.
  zodToJsonSchema(scenarioFileSchema as never, {
    name: 'PlancraftScenario',
    definitions: {
      PlancraftEventFragment: eventFragmentFileSchema as never,
    },
  }) as Record<string, unknown>

// CLI entry: writes docs/scenario.schema.json when run directly.
if (require.main === module) {
  const outDir = path.join(__dirname, '..', '..', 'docs')
  fs.mkdirSync(outDir, { recursive: true })
  const outPath = path.join(outDir, 'scenario.schema.json')
  fs.writeFileSync(
    outPath,
    JSON.stringify(getScenarioJsonSchema(), null, 2) + '\n',
  )
  // eslint-disable-next-line no-console
  console.log(`Wrote ${outPath}`)
}
