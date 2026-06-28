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

export interface AcquireResult {
  status: 'done' | 'running' | 'busy' | 'error' | 'timeout'
  message?: string
  preview?: Preview
  host_path?: string
  total_frames?: number
  integration_time_unit?: string
  bytes?: number
  mode?: string
}

export type WsMessage =
  | { type: 'busy'; mode: string; progress: number }
  | { type: 'state'; data: Record<string, unknown> }
  | { type: 'preview'; data: Preview }
  | { type: 'progress'; data: Record<string, unknown> }
  | { type: 'alarm'; data: Record<string, unknown> }
