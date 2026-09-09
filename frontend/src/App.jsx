import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchApi } from './api.js'
import { DAYS, DAY_NAMES, joinDemand, formatCount } from './demand.js'
import TimeControls from './components/TimeControls.jsx'
import DemandMap from './components/DemandMap.jsx'
import RecommendationPanel from './components/RecommendationPanel.jsx'
import { getNYCTime } from './nycTime.js'

export default function App() {
  const [initialNYCTime] = useState(() => getNYCTime())
  const [day, setDay] = useState(initialNYCTime.day)
  const [hour, setHour] = useState(initialNYCTime.hour)
  const [zones, setZones] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(false)
  const [zoneError, setZoneError] = useState(false)
  const [retry, setRetry] = useState(0)
  const [selected, setSelected] = useState(null)
  const selectZone = useCallback(id => setSelected(id), [])
  useEffect(() => {
    const controller = new AbortController()
    setZoneError(false)
    fetchApi('/api/zones', controller.signal).then(data => {
      if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) throw new Error('Invalid zones')
      setZones(data)
    }).catch(err => { if (err.name !== 'AbortError') setZoneError(true) })
    return () => controller.abort()
  }, [retry])
  useEffect(() => {
    const controller = new AbortController()
    setError(false)
    setResult(null)
    const timeout = setTimeout(async () => {
      try {
        const query = `day=${day}&hour=${hour}`
        const [demand, recommend] = await Promise.all([
          fetchApi(`/api/demand?${query}`, controller.signal),
          fetchApi(`/api/recommend?${query}&top=5`, controller.signal),
        ])
        if (!Array.isArray(demand.data) || !Array.isArray(recommend.recommendations)) throw new Error('Invalid predictions')
        if (!controller.signal.aborted) setResult({ day, hour, rows: demand.data, recommendations: recommend.recommendations })
      } catch (err) { if (err.name !== 'AbortError') setError(true) }
    }, 180)
    return () => { clearTimeout(timeout); controller.abort() }
  }, [day, hour, retry])
  const current = result?.day === day && result?.hour === hour ? result : null
  const joined = useMemo(() => zones && current ? joinDemand(zones, current.rows) : null, [zones, current])
  const names = useMemo(() => new Map(zones?.features.map(f => [Number(f.properties?.LocationID), f.properties?.zone]) || []), [zones])
  const dayName = DAY_NAMES[DAYS.indexOf(day)]
  return <div className="app-shell"><header className="site-header"><div className="brand-icon" aria-hidden="true">↗</div><div><span className="eyebrow">NYC / MOBILITY INTELLIGENCE</span><h1>Ride-Hailing Demand Predictor</h1><p>AI-powered NYC taxi demand forecasting</p></div><div className="model-badge"><span />Random Forest model</div></header>
    <main><TimeControls day={day} hour={hour} onDay={setDay} onHour={setHour} initialNYCTime={initialNYCTime.label} />
      <div className="section-intro"><div><span className="eyebrow">A CLEARER VIEW OF THE CITY</span><h2>Find where demand is heading.</h2></div><p>Real taxi zones. Model-based predictions.<br />A better-informed next move.</p></div>
      {error || zoneError ? <div className="state-card card" role="alert"><h2>Unable to connect to the prediction server.</h2><p>Check that the backend is running, then try again.</p><button onClick={() => { setZones(null); setRetry(n => n + 1) }}>Retry</button></div>
      : !joined ? <div className="state-card card" role="status"><span className="spinner" />Loading demand data...</div>
      : !current.rows.length ? <div className="state-card card" role="status">No demand data available.</div>
      : <><div className="dashboard-grid"><DemandMap data={joined} dayName={dayName} hour={hour} selected={selected} onSelect={selectZone} /><RecommendationPanel rows={current.recommendations} names={names} selected={selected} onSelect={selectZone} /></div>
      <div className="insight-strip"><div><span className="eyebrow">COVERAGE</span><strong>{current.rows.length} taxi zones</strong></div><div><span className="eyebrow">HIGHEST PREDICTED DEMAND</span><strong>{formatCount(Math.max(...current.rows.map(r => r.predictedCount)))} <small>pickups / hour</small></strong></div><p>Built from May 2026 NYC Yellow Taxi records.<br />Predictions are historical estimates, not live activity.</p></div></>}
    </main><footer><span>NYC TAXI DEMAND <b> / </b> MAY 2026</span><span>Explore the city. Make an informed move.</span></footer></div>
}
