import type {
  AcquireResult,
  BridgeStatus,
  CalibrationResult,
  CalibrationStatus,
  CalibrationStepResult,
  DCRCurve,
  FLIMIrfParams,
  FLIMParams,
  FLIMResult,
  GatedParams,
  IntensityParams,
  OptimalParams,
  Raw1BitParams,
  SystemInfo,
} from './types'

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${path} -> ${res.status}${detail ? `: ${detail}` : ''}`)
  }
  return (await res.json()) as T
}

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

export function acquireIntensity(params: IntensityParams): Promise<AcquireResult> {
  return postJson<AcquireResult>('/api/acquire/intensity', params)
}

export function acquireRaw1Bit(params: Raw1BitParams): Promise<AcquireResult> {
  return postJson<AcquireResult>('/api/acquire/raw-1bit', params)
}

export function acquireGated(params: GatedParams): Promise<AcquireResult> {
  return postJson<AcquireResult>('/api/acquire/gated', params)
}

export function getOptimalParams(): Promise<OptimalParams> {
  return getJson<OptimalParams>('/api/acquire/gated/optimal-params')
}

export function calibrateFlimIrf(params: FLIMIrfParams): Promise<CalibrationResult> {
  return postJson<CalibrationResult>('/api/calibrate/flim-irf', params)
}

export function acquireFlim(params: FLIMParams): Promise<FLIMResult> {
  return postJson<FLIMResult>('/api/acquire/flim', params)
}

export function getCalibrationStatus(): Promise<CalibrationStatus> {
  return getJson<CalibrationStatus>('/api/calibration/status')
}

export function getDcrCurve(): Promise<DCRCurve> {
  return getJson<DCRCurve>('/api/calibration/dcr-curve')
}

export function calibrateBreakdown(): Promise<CalibrationStepResult> {
  return postJson<CalibrationStepResult>('/api/calibrate/breakdown', {})
}

export function calibrateNoise(): Promise<CalibrationStepResult> {
  return postJson<CalibrationStepResult>('/api/calibrate/noise', {})
}

export function calibrateDeadPixel(): Promise<CalibrationStepResult> {
  return postJson<CalibrationStepResult>('/api/calibrate/dead-pixel', {})
}

export function calibrateMasterSlaveOffset(): Promise<CalibrationStepResult> {
  return postJson<CalibrationStepResult>('/api/calibrate/master-slave-offset', {})
}

export function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws`
}
