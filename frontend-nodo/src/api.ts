import type { HealthResponse, PedidosResponse } from './types'

/** Base del API. Vacío = mismo origen (Vite proxy en dev, NGINX en prod). */
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

async function getJson<T>(path: string): Promise<{ data: T; http: number }> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
  })
  const text = await res.text()
  let body: unknown
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    throw Object.assign(new Error('Respuesta no válida del servicio'), { http: res.status })
  }
  if (!res.ok) {
    throw Object.assign(new Error(`Error HTTP ${res.status}`), { http: res.status, body })
  }
  return { data: body as T, http: res.status }
}

export function fetchPedidos() {
  return getJson<PedidosResponse>('/pedidos')
}

export function fetchHealth() {
  return getJson<HealthResponse>('/health')
}

export function apiBaseLabel() {
  return API_BASE || '(mismo origen)'
}
