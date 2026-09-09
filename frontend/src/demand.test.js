import test from 'node:test'
import assert from 'node:assert/strict'
import { joinDemand, demandColor } from './demand.js'

test('join uses LocationID rather than feature order and keeps geometry untouched', () => {
  const geometry = { type: 'Polygon', coordinates: [] }
  const source = { type: 'FeatureCollection', features: [161, 1, 9].map(id => ({ properties: { LocationID: id }, geometry })) }
  const result = joinDemand(source, [{ zoneId: 1, predictedCount: 5 }, { zoneId: 161, predictedCount: 400 }])
  assert.deepEqual(result.features.map(f => f.properties.predictedCount), [400, 5, null])
  assert.equal(result.features[0].geometry, geometry)
  assert.equal(source.features[0].properties.predictedCount, undefined)
})

test('fixed color bins include zero and distinguish missing data', () => {
  assert.equal(demandColor(0), '#ccece4')
  assert.equal(demandColor(10), '#77cbb7')
  assert.equal(demandColor(50), '#299e88')
  assert.equal(demandColor(150), '#075c51')
  assert.equal(demandColor(null), '#d5dae0')
})
