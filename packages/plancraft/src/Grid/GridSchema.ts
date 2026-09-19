import { z } from 'zod'
import { authoredScenarioFileSchema } from '../Schema/ScenarioSchema'

// A grid file defines a full-factorial sweep: a base scenario plus named
// dimensions, each with variants that overlay the base (same merge semantics
// as scenario composition: events merge by id, other fields deep-merge).
// The cross product of one variant per dimension yields the scenario set.

const _agePatch = z.object({
  years: z.number().int().gte(0).lte(115),
  months: z.number().int().gte(0).lte(11).optional(),
})
const _personPatch = z.object({
  currentAge: _agePatch.optional(),
  retirementAge: _agePatch.optional(),
  maxAge: _agePatch.optional(),
})
// Deep-partial household so a variant can patch a single field (e.g. only
// person1.retirementAge). The merged combo is re-validated in full.
const _householdPatch = z
  .object({
    person1: _personPatch.optional(),
    person2: _personPatch.optional(),
    withdrawalStart: z.enum(['person1', 'person2']).optional(),
  })
  .optional()

const variantOverlay = z
  .object({
    id: z.string().regex(/^[a-zA-Z0-9_-]{1,40}$/),
    name: z.string().min(1).max(60).describe('Short display name.'),
    events: authoredScenarioFileSchema.shape.events
      .describe('Events merged into the base by id (same id replaces).'),
    excludeEventIds: z.array(z.string()).optional(),
    household: _householdPatch,
    portfolio: authoredScenarioFileSchema.shape.portfolio,
    simulation: authoredScenarioFileSchema.shape.simulation,
  })
  .describe('One choice within a dimension; an overlay on the base scenario.')
export type GridVariant = z.infer<typeof variantOverlay>

export const gridFileSchema = z.object({
  plancraftGrid: z.literal(1),
  name: z.string().min(1).max(80),
  description: z.string().max(2000).optional(),
  base: z.string().describe('Relative path to the base scenario file.'),
  dimensions: z
    .array(
      z.object({
        id: z.string().regex(/^[a-zA-Z0-9_-]{1,40}$/),
        name: z.string().min(1).max(60),
        variants: z.array(variantOverlay).min(1).max(8),
      }),
    )
    .min(1)
    .max(6),
  // Conditions are states of the world (e.g. return assumptions), not
  // decisions: every decision combo is run once per condition, and the
  // report asks whether the decision ranking is stable across them.
  conditions: z
    .array(
      z.object({
        id: z.string().regex(/^[a-zA-Z0-9_-]{1,40}$/),
        name: z.string().min(1).max(60),
        simulation: authoredScenarioFileSchema.shape.simulation,
      }),
    )
    .min(1)
    .max(6)
    .optional(),
})
export type GridFile = z.infer<typeof gridFileSchema>
export type GridCondition = NonNullable<GridFile['conditions']>[number]
