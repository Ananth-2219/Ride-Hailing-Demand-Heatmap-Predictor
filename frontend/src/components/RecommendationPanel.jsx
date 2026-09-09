import { formatCount, demandColor } from '../demand.js'

export default function RecommendationPanel({ rows, names, selected, onSelect }) {
  const maximum = Math.max(...rows.map(row => row.predictedCount), 1)
  return <aside className="card recommendations"><div className="panel-heading"><h2>Top demand zones</h2><p>Highest predicted pickups for this hour.</p></div>
    <ol>{rows.map((row, index) => <li key={row.zoneId}><button className={`recommendation ${selected === row.zoneId ? 'active' : ''}`} onClick={() => onSelect(row.zoneId)}>
      <span className="rank">{String(index + 1).padStart(2, '0')}</span><span className="recommendation-body"><strong>{row.zoneName || names.get(row.zoneId) || `Zone ${row.zoneId}`}</strong><span className="pickup-value">{formatCount(row.predictedCount)} <small>predicted pickups</small></span><span className="bar"><span style={{ width: `${row.predictedCount / maximum * 100}%`, background: demandColor(row.predictedCount) }} /></span></span><span className="arrow" aria-hidden="true">↗</span>
    </button></li>)}</ol>
    <div className="panel-note"><span aria-hidden="true">◎</span><p>Select a zone to explore it on the map.</p></div>
  </aside>
}
