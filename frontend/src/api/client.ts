import type { AcquireResult, BridgeStatus, IntensityParams, SystemInfo } from './types'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return (await res.json()) as T
}

export function getStatus(): Promise<BridgeStatus> {
  return getJson<BridgeStatus>('/api/status')
}

export function getSystemInfo(): Promise<SystemInfo> {
  return getJson<SystemInfo>('/api/system/info')
}

export async function acquireIntensity(params: IntensityParams): Promise<AcquireResult> {
  const res = await fetch('/api/acquire/intensity', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(params),
  })
  return (await res.json()) as AcquireResult
}

export function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws`
}
