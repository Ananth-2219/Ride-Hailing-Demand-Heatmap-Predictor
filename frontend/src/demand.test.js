import test from 'node:test'
import assert from 'node:assert/strict'
import { joinDemand, demandColor, LEVELS } from './demand.js'
import { getNYCTime } from './nycTime.js'

test('NYC weekday and hour respect date rollover, midnight, noon, and DST', () => {
  const cases = [
    ['2026-09-09T22:30:00Z', 'Wed', 18],
    ['2026-01-07T23:30:00Z', 'Wed', 18],
    ['2026-09-10T02:30:00Z', 'Wed', 22],
    ['2026-09-10T04:00:00Z', 'Thu', 0],
    ['2026-09-10T16:00:00Z', 'Thu', 12],
    ['2026-03-08T06:59:00Z', 'Sun', 1],
    ['2026-03-08T07:00:00Z', 'Sun', 3],
    ['2026-11-01T05:30:00Z', 'Sun', 1],
    ['2026-11-01T06:30:00Z', 'Sun', 1],
  ]
  for (const [instant, day, hour] of cases) {
    const actual = getNYCTime(new Date(instant))
    assert.equal(actual.day, day, instant)
    assert.equal(actual.hour, hour, instant)
  }
  assert.equal(getNYCTime(new Date('2026-09-09T22:30:00Z')).label, 'Wed, 18:30')
})

test('join uses LocationID rather than feature order and keeps geometry untouched', () => {
  const geometry = { type: 'Polygon', coordinates: [] }
  const source = { type: 'FeatureCollection', features: [161, 1, 9].map(id => ({ properties: { LocationID: id }, geometry })) }
  const result = joinDemand(source, [{ zoneId: 1, predictedCount: 5 }, { zoneId: 161, predictedCount: 400 }])
  assert.deepEqual(result.features.map(f => f.properties.predictedCount), [400, 5, null])
  assert.equal(result.features[0].geometry, geometry)
  assert.equal(source.features[0].properties.predictedCount, undefined)
})

test('eight fixed bins cover fractional boundaries and distinguish missing data', () => {
  assert.equal(LEVELS.length, 8)
  assert.equal(new Set(LEVELS.map(level => level.color)).size, 8)
  let previous = 0
  LEVELS.forEach(level => {
    assert.equal(demandColor(previous + 0.001), level.color)
    if (Number.isFinite(level.max)) assert.equal(demandColor(level.max), level.color)
    previous = level.max
  })
  assert.equal(demandColor(0), LEVELS[0].color)
  assert.equal(demandColor(250), LEVELS[6].color)
  for (const missing of [null, undefined, NaN, Infinity, -1]) {
    assert.equal(demandColor(missing), '#d5dae0')
  }
})
