const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export async function fetchApi(path, signal) {
  const response = await fetch(`${BASE_URL}${path}`, { signal })
  if (!response.ok) throw new Error(`Prediction server returned ${response.status}`)
  return response.json()
}
