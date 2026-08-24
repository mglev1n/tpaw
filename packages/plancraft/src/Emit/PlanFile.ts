import {
  PlanParams,
  planParamsBackwardsCompatibleGuard,
  SomePlanParams,
} from '@tpaw/common'
import jsonpatch, { Operation } from 'fast-json-patch'
import * as uuid from 'uuid'

// The .tpaw.txt plan file format, replicated from
// packages/web/src/Pages/PlanRoot/PlanRootFile/PlanFileData.tsx. A plan file
// is a human-readable preamble followed by JSON holding a params history as
// jsonpatch diffs; ours has a single 'start' entry, exactly like the web
// app's PlanFileDataFns.getNew().

export const PLAN_FILE_EXTENSION = '.tpaw.txt'

// Must match the prefix in PlanFileData.tsx for cosmetic parity (the parser
// only scans to the first '{').
const PREFIX = `
HOW TO OPEN THIS FILE
---------------------

This file contains a plan from TPAW Planner.
You can open this plan from the plan menu at:

https://tpawplanner.com/plan


---- PLAN DATA STARTS HERE ----
`

type Stored = {
  v: 1
  convertedToFilePlanAtTimestamp: number
  lastSavedTimestamp: number
  planParamsHistory: {
    id: string
    change: { type: 'start'; value: null }
    diff: Operation[]
  }[]
  reverseHeadIndex: number
}

export const getPlanFileContent = (planParams: PlanParams): string => {
  const stored: Stored = {
    v: 1,
    convertedToFilePlanAtTimestamp: planParams.timestamp,
    lastSavedTimestamp: planParams.timestamp,
    planParamsHistory: [
      {
        id: uuid.v4(),
        change: { type: 'start', value: null },
        diff: jsonpatch.compare({}, planParams),
      },
    ],
    reverseHeadIndex: 0,
  }
  const content = `${PREFIX}${JSON.stringify(stored)}`
  // Self-check: re-parse the way the web app's open() does.
  const reParsed = parsePlanFileContent(content)
  if (reParsed === null)
    throw new Error('Internal error: generated plan file failed to re-parse.')
  return content
}

// Mirror of the open-side logic: scan to the first '{', apply patches
// cumulatively from {}, validate with the backwards-compatible guard.
export const parsePlanFileContent = (content: string): SomePlanParams | null => {
  const startIndex = content.indexOf('{')
  if (startIndex === -1) return null
  let stored: Stored
  try {
    stored = JSON.parse(content.slice(startIndex)) as Stored
  } catch {
    return null
  }
  if (stored.v !== 1 || stored.planParamsHistory.length === 0) return null
  const curr = {} as Record<string, unknown>
  let last: SomePlanParams | null = null
  for (const entry of stored.planParamsHistory) {
    try {
      jsonpatch.applyPatch(curr, entry.diff)
    } catch {
      return null
    }
    const check = planParamsBackwardsCompatibleGuard(
      JSON.parse(JSON.stringify(curr)),
    )
    if (check.error) return null
    last = check.value
  }
  return last
}
