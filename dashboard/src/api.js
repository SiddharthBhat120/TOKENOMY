// Same origin when served by FastAPI at /dashboard/; localhost:8000 during `npm run dev`.
export const API = import.meta.env.VITE_API ?? (location.port === '5173' ? 'http://localhost:8000' : '')

export async function get(path) {
  const r = await fetch(API + path)
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}

export async function post(path, body, headers = {}) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  const h = {}
  r.headers.forEach((v, k) => { if (k.startsWith('x-tokenomy')) h[k] = v })
  return { ok: r.ok, status: r.status, data, headers: h }
}

// money: costs per request are tiny, so precision adapts to size
export function usd(v, { compact = false } = {}) {
  if (v == null || isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a === 0) return '$0'
  if (a >= 100) return '$' + v.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (a >= 1) return '$' + v.toFixed(2)
  if (a >= 0.01) return '$' + v.toFixed(compact ? 3 : 4)
  const digits = Math.min(10, Math.ceil(-Math.log10(a)) + 2)
  return '$' + v.toFixed(digits)
}

export const pct = (v) => (v == null ? '—' : `${(+v).toFixed(1)}%`)
export const ms = (v) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`)
export const shortModel = (m = '') => m.replace(/^ollama\//, '').replace(/^.*\//, '')
