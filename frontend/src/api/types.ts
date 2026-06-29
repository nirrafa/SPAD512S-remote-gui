export interface Preview {
  width: number
  height: number
  max_value: number
  data: string // base64 uint8, row-major
}

export interface SystemInfo {
  fpga_serial_master: string
  fpga_serial_slave: string
  sw_version: string
  fw_version: string
  hw_version: string
  hardware_flavour: string
  sensor_size: number
  enabled_features: Record<string, boolean>
  valid_bit_depths: number[]
  valid_roi_widths: number[]
}

export interface BridgeStatus {
  vendor_connected: boolean
  instrument_state: string
}

export interface IntensityParams {
  bit_depth: number
  integration_time: number
  iterations: number
  roi_width: number
  overlap: boolean
  pileup_correction: boolean
  timeout_s?: number
}

export interface Raw1BitParams {
  integration_time_us: number
  iterations: number
  roi_width: number
  overlap: boolean
  timeout_s?: number
}

export interface AcquireResult {
  status: 'done' | 'running' | 'busy' | 'error' | 'timeout'
  message?: string
  preview?: Preview
  host_path?: string
  total_frames?: number
  total_gate_steps?: number
  previews_sent?: number
  integration_time_unit?: string
  bytes?: number
  mode?: string
  decode_method?: string
  bit_depth?: number
  calibration_valid?: boolean
  warning?: string
}

export interface GatedParams {
  bit_depth: number
  integration_time_ms: number
  iterations: number
  gate_steps: number
  gate_step_size_ps: number
  gate_width: number
  gate_offset: number
  gate_direction: 'forward' | 'reverse'
  gate_trigger_source: 'internal' | 'external'
  overlap: boolean
  stream: boolean
  pileup_correction: boolean
  arbitrary_steps?: number[]
}

export interface OptimalParams {
  steps: number
  offset: number
  min_step: number
}

export interface FLIMIrfParams {
  calibration_type: 'mono_exponential' | 'bi_exponential'
  expected_tau_ns: number | number[]
  gate_width: 'short' | 'medium' | 'long'
}

export interface FLIMParams {
  integration_time_ms: number
  gate_subsampling: number
  output_format: 'image' | 'raw'
}

export interface PhasorData {
  g: number[]
  s: number[]
}

export interface CalibrationResult {
  status: 'done' | 'error'
  message?: string
  calibration_type?: string
  gate_width?: string
}

export interface FLIMResult {
  status: 'done' | 'error'
  message?: string
  warning?: string
  phasor?: PhasorData
  lifetime_map?: Preview
  preview?: Preview
  total_gate_steps?: number
  output_format?: string
}

export type CalibrationKind =
  | 'breakdown'
  | 'noise'
  | 'dead_pixel'
  | 'master_slave_offset'
  | 'flim_irf'

export interface CalibrationEntry {
  state: 'none' | 'running' | 'done' | 'failed'
  timestamp?: number
  stale?: boolean
}

export type CalibrationStatus = Record<CalibrationKind, CalibrationEntry>

export interface CalibrationStepResult {
  status: 'done' | 'error'
  message?: string
  setup_prompt?: string
}

export interface DCRCurve {
  percentages: number[]
  dcr_values: number[]
}

export type WsMessage =
  | { type: 'busy'; mode: string; progress: number }
  | { type: 'state'; data: Record<string, unknown> }
  | { type: 'preview'; data: Preview }
  | { type: 'progress'; data: Record<string, unknown> }
  | { type: 'alarm'; data: Record<string, unknown> }
