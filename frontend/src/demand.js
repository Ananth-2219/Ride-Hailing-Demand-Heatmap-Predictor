export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
export const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export const hourLabel = hour => `${String(hour).padStart(2, '0')}:00`
export const formatCount = count => Number.isFinite(count) ? count.toLocaleString('en-US', { maximumFractionDigits: 1, minimumFractionDigits: 1 }) : 'Unavailable'
// Fixed upper bounds include fractional predictions without gaps between bins.
export const LEVELS = [
  { max: 5, range: '0–5', color: '#7198f7' },
  { max: 20, range: '>5–20', color: '#55c8df' },
  { max: 50, range: '>20–50', color: '#65d5ba' },
  { max: 100, range: '>50–100', color: '#b7df72' },
  { max: 150, range: '>100–150', color: '#f4df54' },
  { max: 200, range: '>150–200', color: '#ffb448' },
  { max: 300, range: '>200–300', color: '#fa7950' },
  { max: Infinity, range: '>300', color: '#d8304e' },
]
export function demandColor(count) {
  if (!Number.isFinite(count) || count < 0) return '#d5dae0'
  return LEVELS.find(level => count <= level.max).color
}
export function joinDemand(geojson, rows) {
  const byId = new Map(rows.map(row => [Number(row.zoneId), row.predictedCount]))
  return { ...geojson, features: geojson.features.map(feature => ({ ...feature,
    properties: { ...feature.properties, predictedCount: byId.get(Number(feature.properties?.LocationID)) ?? null },
  })) }
}
