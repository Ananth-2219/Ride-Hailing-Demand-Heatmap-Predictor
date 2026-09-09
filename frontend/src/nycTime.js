// Capture one instant so the weekday, hour, and displayed time always agree.
export function getNYCTime(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23', // Midnight must be 00, not 24.
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return {
    day: values.weekday,
    hour: Number(values.hour),
    label: `${values.weekday}, ${values.hour}:${values.minute}`,
  }
}
