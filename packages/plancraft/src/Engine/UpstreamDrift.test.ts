import fs from 'fs'
import path from 'path'

// The files in this directory are verbatim copies of the web package's
// simulator client (see the plancraft README). If web's copies change (e.g.
// after merging upstream), this test fails so the copies get re-synced:
//
//   cp ../web/src/Simulator/SimulateOnServer/GetPlanParamsServer.ts src/Engine/
//   cp ../web/src/Simulator/SimulateOnServer/DeWire.ts src/Engine/
//   cp ../web/src/Simulator/SimulateOnServer/DeWire.test.ts src/Engine/
//   cp -r ../web/src/Simulator/SimulateOnServer/Wire src/Engine/

const webDir = path.join(
  __dirname,
  '..',
  '..',
  '..',
  'web',
  'src',
  'Simulator',
  'SimulateOnServer',
)
const localDir = __dirname

const filesToCompare = [
  'GetPlanParamsServer.ts',
  'DeWire.ts',
  'DeWire.test.ts',
  ...fs
    .readdirSync(path.join(webDir, 'Wire'))
    .map((x) => path.join('Wire', x)),
]

describe('copies of web simulator client are in sync', () => {
  test.each(filesToCompare)('%s', (relative) => {
    const web = fs.readFileSync(path.join(webDir, relative), 'utf8')
    const local = fs.readFileSync(path.join(localDir, relative), 'utf8')
    expect(local).toBe(web)
  })
})
