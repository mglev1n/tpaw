import _ from 'lodash'
import { z } from 'zod'
import {
  AuthoredScenarioFile,
  authoredScenarioFileSchema,
  eventFragmentFileSchema,
  ScenarioEvent,
  ScenarioFile,
  scenarioFileSchema,
} from '../Schema/ScenarioSchema'

export class ScenarioError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ScenarioError'
  }
}

const MAX_DEPTH = 10

const _parseJson = (path: string, content: string): unknown => {
  try {
    return JSON.parse(content)
  } catch (e) {
    throw new ScenarioError(
      `${path}: not valid JSON (${e instanceof Error ? e.message : String(e)})`,
    )
  }
}

const _zodIssues = (path: string, error: z.ZodError): string =>
  error.issues
    .map((x) => `${path}: ${x.path.join('.') || '(root)'}: ${x.message}`)
    .join('\n')

// Merge b into a. Objects merge deep, arrays and scalars replace. Events are
// handled separately (by id) and must not be passed through here.
export const mergeNonEventFields = <T>(a: T, b: T): T =>
  _.mergeWith(_.cloneDeep(a), b, (_aVal, bVal) =>
    Array.isArray(bVal) ? bVal : undefined,
  )
const _mergeNonEventFields = mergeNonEventFields

export const mergeEventsById = (
  base: ScenarioEvent[],
  overlay: ScenarioEvent[],
): ScenarioEvent[] => {
  const result = [...base]
  for (const event of overlay) {
    const i = result.findIndex((x) => x.id === event.id)
    if (i === -1) result.push(event)
    else result[i] = event
  }
  return result
}

// Resolves a scenario file's composition (extends / include / excludeEventIds)
// into a single flat, fully-validated scenario. File access is injected so
// this stays a pure function for testing.
export const resolveScenario = (
  entryPath: string,
  readFile: (path: string) => string,
  resolvePath: (fromFile: string, relative: string) => string,
): ScenarioFile => {
  const resolved = _resolveAuthored(
    entryPath,
    readFile,
    resolvePath,
    new Set(),
    0,
  )

  const check = scenarioFileSchema.safeParse(resolved)
  if (!check.success) {
    throw new ScenarioError(
      `Resolved scenario from ${entryPath} is incomplete or invalid:\n` +
        _zodIssues(entryPath, check.error),
    )
  }
  const scenario = check.data

  const duplicate = _.chain(scenario.events)
    .countBy((x) => x.id)
    .pickBy((n) => n > 1)
    .keys()
    .value()
  if (duplicate.length > 0)
    throw new ScenarioError(
      `${entryPath}: duplicate event ids after resolution: ${duplicate.join(', ')}`,
    )
  return scenario
}

const _resolveAuthored = (
  path: string,
  readFile: (path: string) => string,
  resolvePath: (fromFile: string, relative: string) => string,
  visiting: Set<string>,
  depth: number,
): Omit<AuthoredScenarioFile, 'composition'> => {
  if (depth > MAX_DEPTH)
    throw new ScenarioError(`${path}: composition nesting exceeds ${MAX_DEPTH}`)
  if (visiting.has(path))
    throw new ScenarioError(`${path}: circular composition ('extends' cycle)`)
  visiting.add(path)

  const parsed = authoredScenarioFileSchema.safeParse(
    _parseJson(path, readFile(path)),
  )
  if (!parsed.success)
    throw new ScenarioError(_zodIssues(path, parsed.error))
  const authored = parsed.data
  const { composition, ...ownFields } = authored

  let base: Omit<AuthoredScenarioFile, 'composition'> | null = null
  if (composition?.extends) {
    base = _resolveAuthored(
      resolvePath(path, composition.extends),
      readFile,
      resolvePath,
      visiting,
      depth + 1,
    )
  }

  const { events: ownEvents, ...ownNonEvent } = ownFields
  const { events: baseEvents, ...baseNonEvent } = base ?? { events: undefined }

  const merged: Omit<AuthoredScenarioFile, 'composition'> = {
    ..._mergeNonEventFields(baseNonEvent as typeof ownNonEvent, ownNonEvent),
    events: mergeEventsById(baseEvents ?? [], ownEvents ?? []),
  }

  for (const includePath of composition?.include ?? []) {
    const fragmentPath = resolvePath(path, includePath)
    const fragmentParsed = eventFragmentFileSchema.safeParse(
      _parseJson(fragmentPath, readFile(fragmentPath)),
    )
    if (!fragmentParsed.success)
      throw new ScenarioError(_zodIssues(fragmentPath, fragmentParsed.error))
    merged.events = mergeEventsById(
      merged.events ?? [],
      fragmentParsed.data.events,
    )
  }

  if (composition?.excludeEventIds) {
    const present = new Set((merged.events ?? []).map((x) => x.id))
    const missing = composition.excludeEventIds.filter((x) => !present.has(x))
    if (missing.length > 0)
      throw new ScenarioError(
        `${path}: excludeEventIds not found: ${missing.join(', ')}`,
      )
    const exclude = new Set(composition.excludeEventIds)
    merged.events = (merged.events ?? []).filter((x) => !exclude.has(x.id))
  }

  visiting.delete(path)
  return merged
}
