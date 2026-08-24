import _ from 'lodash'
import { z } from 'zod'
import {
  mergeEventsById,
  mergeNonEventFields,
  resolveScenario,
  ScenarioError,
} from '../Compile/ResolveScenario'
import { ScenarioFile, scenarioFileSchema } from '../Schema/ScenarioSchema'
import { GridCondition, GridFile, gridFileSchema, GridVariant } from './GridSchema'

export type GridCombo = {
  // dimension id -> variant id
  cells: Record<string, string>
  // dimension id -> variant display name
  cellNames: Record<string, string>
  name: string
  scenario: ScenarioFile
}

export type GeneratedGrid = {
  grid: GridFile
  base: ScenarioFile
  combos: GridCombo[]
  // At least one; a single no-op "base" condition when the grid file has none.
  conditions: GridCondition[]
}

// A condition overlays only simulation settings onto a combo's scenario.
export const applyCondition = (
  scenario: ScenarioFile,
  condition: GridCondition,
): ScenarioFile =>
  condition.simulation === undefined
    ? scenario
    : {
        ...scenario,
        simulation: mergeNonEventFields(
          scenario.simulation ?? {},
          condition.simulation,
        ),
      }

const _applyVariant = (scenario: ScenarioFile, variant: GridVariant): ScenarioFile => {
  const { events, excludeEventIds, id: _id, name: _name, ...nonEvent } = variant
  // The overlay is deep-partial; every combo is re-validated against the full
  // schema after generation, so the cast is checked downstream.
  const result: ScenarioFile = {
    ...(mergeNonEventFields(
      scenario as unknown as Record<string, unknown>,
      _.omitBy(nonEvent, (v) => v === undefined),
    ) as unknown as ScenarioFile),
    events: mergeEventsById(scenario.events, events ?? []),
  }
  if (excludeEventIds && excludeEventIds.length > 0) {
    // Lenient: an id another dimension may or may not have added (e.g. a
    // career-boost event absent in the baseline career) is skipped silently.
    const exclude = new Set(excludeEventIds)
    result.events = result.events.filter((x) => !exclude.has(x.id))
  }
  return result
}

export const generateGrid = (
  gridPath: string,
  readFile: (path: string) => string,
  resolvePath: (fromFile: string, relative: string) => string,
): GeneratedGrid => {
  let parsedJson: unknown
  try {
    parsedJson = JSON.parse(readFile(gridPath))
  } catch (e) {
    throw new ScenarioError(
      `${gridPath}: not valid JSON (${e instanceof Error ? e.message : String(e)})`,
    )
  }
  const parsed = gridFileSchema.safeParse(parsedJson)
  if (!parsed.success)
    throw new ScenarioError(
      parsed.error.issues
        .map((x: z.ZodIssue) => `${gridPath}: ${x.path.join('.')}: ${x.message}`)
        .join('\n'),
    )
  const grid = parsed.data

  const base = resolveScenario(
    resolvePath(gridPath, grid.base),
    readFile,
    resolvePath,
  )

  let combos: GridCombo[] = [
    { cells: {}, cellNames: {}, name: '', scenario: base },
  ]
  for (const dimension of grid.dimensions) {
    combos = combos.flatMap((combo) =>
      dimension.variants.map((variant): GridCombo => {
        const scenario = _applyVariant(combo.scenario, variant)
        const name = combo.name
          ? `${combo.name} · ${variant.name}`
          : variant.name
        return {
          cells: { ...combo.cells, [dimension.id]: variant.id },
          cellNames: { ...combo.cellNames, [dimension.id]: variant.name },
          name,
          scenario: {
            ...scenario,
            // meta.name is capped at 80 chars; combo.name keeps the full name.
            meta: { ...scenario.meta, name: name.slice(0, 80), description: undefined },
          },
        }
      }),
    )
  }

  // Validate every combo against the full schema (composition guarantees it
  // structurally, but variant overlays can introduce inconsistencies).
  for (const combo of combos) {
    const check = scenarioFileSchema.safeParse(combo.scenario)
    if (!check.success)
      throw new ScenarioError(
        `Grid combo '${combo.name}' is invalid:\n` +
          check.error.issues
            .map((x: z.ZodIssue) => `  ${x.path.join('.')}: ${x.message}`)
            .join('\n'),
      )
    combo.scenario = check.data
  }
  const conditions: GridCondition[] = grid.conditions ?? [
    { id: 'base', name: 'Base', simulation: undefined },
  ]
  return { grid, base, combos, conditions }
}
