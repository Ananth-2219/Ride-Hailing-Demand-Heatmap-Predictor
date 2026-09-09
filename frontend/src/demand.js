export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
export const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export const hourLabel = hour => `${String(hour).padStart(2, '0')}:00`
export const formatCount = count => Number.isFinite(count) ? count.toLocaleString('en-US', { maximumFractionDigits: 1, minimumFractionDigits: 1 }) : 'Unavailable'
export const LEVELS = [
  { label: 'Low', range: '0–<10', color: '#ccece4' },
  { label: 'Medium', range: '10–<50', color: '#77cbb7' },
  { label: 'High', range: '50–<150', color: '#299e88' },
  { label: 'Very high', range: '150+', color: '#075c51' },
]
export function demandColor(count) {
  if (!Number.isFinite(count)) return '#d5dae0'
  return LEVELS[count >= 150 ? 3 : count >= 50 ? 2 : count >= 10 ? 1 : 0].color
}
export function joinDemand(geojson, rows) {
  const byId = new Map(rows.map(row => [Number(row.zoneId), row.predictedCount]))
  return { ...geojson, features: geojson.features.map(feature => ({ ...feature,
    properties: { ...feature.properties, predictedCount: byId.get(Number(feature.properties?.LocationID)) ?? null },
  })) }
}
