import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import { demandColor, formatCount, hourLabel, LEVELS } from '../demand.js'

function ZoneLayer({ data, dayName, hour, selected, onSelect }) {
  const map = useMap()
  const layerRef = useRef()
  useEffect(() => {
    const layer = layerRef.current
    layer.eachLayer(polygon => polygon.closeTooltip())
    layer.clearLayers()
    layer.addData(data)
    layer.eachLayer(polygon => {
      const props = polygon.feature.properties
      const id = Number(props.LocationID)
      polygon.setStyle({ fillColor: demandColor(props.predictedCount), fillOpacity: 0.76, color: id === selected ? '#f1ac35' : '#397b70', weight: id === selected ? 3 : 0.7 })
      const tooltip = document.createElement('div')
      const title = document.createElement('strong')
      title.textContent = props.zone || `Zone ${id}`
      tooltip.append(title, document.createElement('br'), `Predicted pickups: ${formatCount(props.predictedCount)}`, document.createElement('br'), `${dayName} · ${hourLabel(hour)}`)
      polygon.bindTooltip(tooltip, { sticky: true })
      polygon.on('click', () => onSelect(id))
      polygon.on('mouseover', () => polygon.setStyle({ weight: 2, fillOpacity: 0.95 }))
      polygon.on('mouseout', () => polygon.setStyle({ weight: id === selected ? 3 : 0.7, fillOpacity: 0.76 }))
      if (id === selected) polygon.bringToFront()
    })
  }, [data, dayName, hour, selected, onSelect, map])
  useEffect(() => {
    if (selected == null) {
      map.fitBounds(L.geoJSON(data).getBounds(), { padding: [20, 20], animate: false })
      return
    }
    const features = data.features.filter(f => Number(f.properties?.LocationID) === selected)
    if (features.length) map.fitBounds(L.geoJSON(features).getBounds(), { padding: [60, 60], maxZoom: 14, animate: false })
  }, [selected, map]) // Changing time preserves the current map view.
  return <GeoJSON ref={layerRef} data={null} />
}

export default function DemandMap({ data, dayName, hour, selected, onSelect }) {
  const [tileError, setTileError] = useState(false)
  const feature = useMemo(() => data.features.find(f => Number(f.properties?.LocationID) === selected), [data, selected])
  return <section className="card map-card"><div className="map-heading"><div><span className="eyebrow">DEMAND EXPLORER</span><h2>New York City <span className="zone-badge">{data.features.length} zones</span></h2></div><span className="time-badge">{dayName} · {hourLabel(hour)}</span></div>
    <div className="map-wrap"><MapContainer center={[40.73, -73.94]} zoom={10} zoomAnimation={false} fadeAnimation={false} scrollWheelZoom className="demand-map" aria-label="NYC taxi-zone demand map">
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' eventHandlers={{ tileerror: () => setTileError(true) }} />
      <ZoneLayer data={data} dayName={dayName} hour={hour} selected={selected} onSelect={onSelect} />
    </MapContainer>{tileError && <div className="tile-notice">Basemap tiles unavailable. Taxi-zone polygons remain interactive.</div>}
    {feature && <div className="selection-card"><button aria-label="Clear selected zone" onClick={() => onSelect(null)}>×</button><span className="eyebrow">SELECTED ZONE · {selected}</span><h3>{feature.properties.zone || `Zone ${selected}`}</h3><strong>{formatCount(feature.properties.predictedCount)} <small>predicted pickups</small></strong><p>{dayName} · {hourLabel(hour)} NYC time</p></div>}</div>
    <div className="legend"><span>Predicted pickups / hour</span><div>{LEVELS.map(level => <span key={level.label}><i style={{ background: level.color }} /><span>{level.label}<small>{level.range}</small></span></span>)}<span><i style={{ background: '#d5dae0' }} /><span>No data</span></span></div></div>
  </section>
}
