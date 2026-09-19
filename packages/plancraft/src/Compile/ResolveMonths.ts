import { Month } from '@tpaw/common'
import { ScenarioError } from './ResolveScenario'
import { ScenarioFile, TimePoint, TimingRange } from '../Schema/ScenarioSchema'

export type PersonAges = {
  currentAgeMonths: number
  // null when already retired at plan start.
  retirementAgeMonths: number | null
  maxAgeMonths: number
}
export type HouseholdAges = {
  person1: PersonAges
  person2: PersonAges | null
}

// The calendar month (1-12) and year that "now" (MFN 0) corresponds to.
export type Anchor = { year: number; month: number }

export const toMonths = (x: { years: number; months?: number }): number =>
  x.years * 12 + (x.months ?? 0)

export const getHouseholdAges = (
  household: ScenarioFile['household'],
): HouseholdAges => {
  const one = (
    p: ScenarioFile['household']['person1'],
    label: string,
  ): PersonAges => {
    const currentAgeMonths = toMonths(p.currentAge)
    const retirementAgeMonths = toMonths(p.retirementAge)
    const maxAgeMonths = toMonths(p.maxAge ?? { years: 100 })
    if (retirementAgeMonths < currentAgeMonths)
      throw new ScenarioError(
        `${label}: retirementAge is before currentAge. For someone already ` +
          'retired, set retirementAge equal to currentAge.',
      )
    if (maxAgeMonths <= Math.max(currentAgeMonths, retirementAgeMonths))
      throw new ScenarioError(`${label}: maxAge must be after retirementAge.`)
    return {
      currentAgeMonths,
      retirementAgeMonths:
        retirementAgeMonths === currentAgeMonths ? null : retirementAgeMonths,
      maxAgeMonths,
    }
  }
  return {
    person1: one(household.person1, 'household.person1'),
    person2: household.person2 ? one(household.person2, 'household.person2') : null,
  }
}

export type ResolvedTimePoint = { month: Month; mfn: number }

const _getPerson = (
  ages: HouseholdAges,
  person: 'person1' | 'person2' | undefined,
  context: string,
): { id: 'person1' | 'person2'; ages: PersonAges } => {
  const id = person ?? 'person1'
  const p = ages[id]
  if (p === null)
    throw new ScenarioError(
      `${context}: refers to person2 but the household has no person2.`,
    )
  return { id, ages: p }
}

export const resolveTimePoint = (
  point: TimePoint,
  ages: HouseholdAges,
  anchor: Anchor,
  context: string,
): ResolvedTimePoint => {
  const asPerson1NumericAge = (mfn: number): ResolvedTimePoint => ({
    mfn,
    month:
      mfn === 0
        ? { type: 'now', monthOfEntry: { isDatedPlan: false } }
        : {
            type: 'numericAge',
            person: 'person1',
            age: { inMonths: ages.person1.currentAgeMonths + mfn },
          },
  })

  if ('calendarYear' in point) {
    const mfn =
      (point.calendarYear - anchor.year) * 12 +
      (point.month ?? 1) -
      anchor.month
    if (mfn < 0)
      throw new ScenarioError(
        `${context}: ${point.calendarYear}-${point.month ?? 1} is in the ` +
          `past relative to the anchor ${anchor.year}-${anchor.month}.`,
      )
    return asPerson1NumericAge(mfn)
  }

  if ('age' in point) {
    const { id, ages: p } = _getPerson(ages, point.age.person, context)
    const inMonths = toMonths(point.age)
    const mfn = inMonths - p.currentAgeMonths
    if (mfn < 0)
      throw new ScenarioError(
        `${context}: age ${point.age.years}y for ${id} is in the past ` +
          `(current age is ${Math.floor(p.currentAgeMonths / 12)}y).`,
      )
    return mfn === 0
      ? { mfn, month: { type: 'now', monthOfEntry: { isDatedPlan: false } } }
      : { mfn, month: { type: 'numericAge', person: id, age: { inMonths } } }
  }

  switch (point.named) {
    case 'now':
      return { mfn: 0, month: { type: 'now', monthOfEntry: { isDatedPlan: false } } }
    case 'retirement':
    case 'lastWorkingMonth': {
      const { id, ages: p } = _getPerson(ages, point.person, context)
      if (p.retirementAgeMonths === null)
        throw new ScenarioError(
          `${context}: '${point.named}' of ${id} is not defined because ` +
            `${id} is already retired. Use {named: 'now'} instead.`,
        )
      const retirementMFN = p.retirementAgeMonths - p.currentAgeMonths
      if (point.named === 'retirement')
        return {
          mfn: retirementMFN,
          month: { type: 'namedAge', person: id, age: 'retirement' },
        }
      if (retirementMFN - 1 < 0)
        throw new ScenarioError(
          `${context}: '${point.named}' of ${id} is in the past.`,
        )
      return {
        mfn: retirementMFN - 1,
        month: { type: 'namedAge', person: id, age: 'lastWorkingMonth' },
      }
    }
    case 'maxAge': {
      const { id, ages: p } = _getPerson(ages, point.person, context)
      return {
        mfn: p.maxAgeMonths - p.currentAgeMonths,
        month: { type: 'namedAge', person: id, age: 'max' },
      }
    }
  }
}

export type ResolvedRange = {
  start: ResolvedTimePoint
  end: ResolvedTimePoint
}

export const resolveTimingRange = (
  range: TimingRange,
  ages: HouseholdAges,
  anchor: Anchor,
  context: string,
): ResolvedRange => {
  const start = resolveTimePoint(range.from, ages, anchor, `${context}.from`)
  if ('durationYears' in range) {
    const durationMonths = Math.max(1, Math.round(range.durationYears * 12))
    const endMFN = start.mfn + durationMonths - 1
    return {
      start,
      end: {
        mfn: endMFN,
        month: {
          type: 'numericAge',
          person: 'person1',
          age: { inMonths: ages.person1.currentAgeMonths + endMFN },
        },
      },
    }
  }
  const end = resolveTimePoint(range.to, ages, anchor, `${context}.to`)
  if (end.mfn < start.mfn)
    throw new ScenarioError(
      `${context}: range ends (MFN ${end.mfn}) before it starts (MFN ${start.mfn}).`,
    )
  return { start, end }
}

// Deterministic 10-char lowercase id derived from a string, so recompiles
// produce identical PlanParams (stable diffs). FNV-1a over the input, twice
// with different seeds, mapped to a-z.
export const deterministicSmallId = (source: string): string => {
  const fnv = (seed: number): number => {
    let hash = seed >>> 0
    for (let i = 0; i < source.length; i++) {
      hash ^= source.charCodeAt(i)
      hash = Math.imul(hash, 0x01000193) >>> 0
    }
    return hash
  }
  const chars = 'abcdefghijklmnopqrstuvwxyz'
  let a = fnv(0x811c9dc5)
  let b = fnv(0x1234567)
  let result = ''
  for (let i = 0; i < 10; i++) {
    const mixed = i % 2 === 0 ? a : b
    result += chars[mixed % 26]
    if (i % 2 === 0) a = Math.floor(a / 26) ^ Math.imul(b, 31)
    else b = Math.floor(b / 26) ^ Math.imul(a, 31)
    a = a >>> 0
    b = b >>> 0
  }
  return result
}
