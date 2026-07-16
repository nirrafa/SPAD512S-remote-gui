import type {
  AcquireResult,
  AcquireStatus,
  BridgeStatus,
  CalibrationResult,
  CalibrationStatus,
  CalibrationStepResult,
  DCRCurve,
  ExperimentLogEntry,
  FLIMIrfParams,
  FLIMParams,
  FLIMResult,
  GatedParams,
  HealthConfig,
  HealthReadings,
  IntensityParams,
  JobStatus,
  LiveFrameParams,
  LiveFrameResult,
  OptimalParams,
  Preset,
  Raw1BitParams,
  ScheduleRequest,
  ScheduleResult,
  StopResult,
  SweepRequest,
  SweepResult,
  SystemInfo,
  VexResult,
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

export function getHealthReadings(): Promise<HealthReadings> {
  return getJson<HealthReadings>('/api/health/readings')
}

export function getHealthConfig(): Promise<HealthConfig> {
  return getJson<HealthConfig>('/api/health/config')
}

export async function updateHealthConfig(
  update: Partial<HealthConfig>,
): Promise<{ status: string }> {
  const res = await fetch('/api/health/config', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(update),
  })
  return (await res.json()) as { status: string }
}

export function setVex(vex: number, confirm = false): Promise<VexResult> {
  return postJson<VexResult>('/api/settings/vex', { vex, confirm })
}

export function acquireSweep(request: SweepRequest): Promise<SweepResult> {
  return postJson<SweepResult>('/api/acquire/sweep', request)
}

export function resumeSweep(): Promise<SweepResult> {
  return postJson<SweepResult>('/api/acquire/sweep/resume', {})
}

export function getAcquireStatus(): Promise<AcquireStatus> {
  return getJson<AcquireStatus>('/api/acquire/status')
}

export function stopAcquisition(): Promise<StopResult> {
  return postJson<StopResult>('/api/acquire/stop', {})
}

export function scheduleJob(request: ScheduleRequest): Promise<ScheduleResult> {
  return postJson<ScheduleResult>('/api/acquire/schedule', request)
}

export function getJobStatus(jobId: string): Promise<JobStatus> {
  return getJson<JobStatus>(`/api/acquire/schedule/${jobId}`)
}

export function captureLiveFrame(params: LiveFrameParams = {}): Promise<LiveFrameResult> {
  return postJson<LiveFrameResult>('/api/live/frame', params)
}

export async function getExperimentLog(opts?: {
  search?: string
  limit?: number
  offset?: number
}): Promise<{ entries: ExperimentLogEntry[] }> {
  const q = new URLSearchParams()
  if (opts?.search) q.set('search', opts.search)
  if (opts?.limit != null) q.set('limit', String(opts.limit))
  if (opts?.offset != null) q.set('offset', String(opts.offset))
  const suffix = q.toString() ? `?${q}` : ''
  return getJson<{ entries: ExperimentLogEntry[] }>(`/api/experiment-log${suffix}`)
}

export function rerunEntry(
  entryId: string,
  overrides: Record<string, unknown> = {},
): Promise<AcquireResult> {
  return postJson<AcquireResult>(`/api/experiment-log/${entryId}/rerun`, { overrides })
}

export function savePreset(
  name: string,
  mode: string,
  params: Record<string, unknown>,
): Promise<{ status: string; preset_id: string }> {
  return postJson('/api/presets', { name, mode, params })
}

export function listPresets(mode: string): Promise<Preset[]> {
  return getJson<Preset[]>(`/api/presets?mode=${encodeURIComponent(mode)}`)
}

export async function deletePreset(presetId: string): Promise<{ status: string }> {
  const res = await fetch(`/api/presets/${presetId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`delete preset -> ${res.status}`)
  return (await res.json()) as { status: string }
}

export function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws`
}
