import { DAYS, DAY_NAMES, hourLabel } from '../demand.js'

export default function TimeControls({ day, hour, onDay, onHour }) {
  return <section className="controls card" aria-label="Prediction time">
    <div className="control-intro"><span className="eyebrow">PLAN YOUR NEXT PICKUP</span><h2>When are you driving?</h2><p>Explore a typical hour in New York City.</p></div>
    <label className="day-control"><span>Day of the week</span><select value={day} onChange={e => onDay(e.target.value)}>{DAYS.map((d, i) => <option key={d} value={d}>{DAY_NAMES[i]}</option>)}</select></label>
    <div className="hour-control"><label htmlFor="hour">Pickup hour <output htmlFor="hour">{hourLabel(hour)} <small>NYC time</small></output></label><input id="hour" aria-label="Pickup hour" type="range" min="0" max="23" value={hour} onChange={e => onHour(Number(e.target.value))} /><div className="range-labels"><span>00:00</span><span>12:00</span><span>23:00</span></div></div>
  </section>
}
