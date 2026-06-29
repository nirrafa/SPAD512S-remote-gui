import { useState } from 'react'
import type { FLIMIrfParams, FLIMParams } from '../api/types'

interface Props {
  disabled: boolean
  calibrated: boolean
  onCalibrate: (params: FLIMIrfParams) => void
  onAcquire: (params: FLIMParams) => void
}

export function FLIMPanel({ disabled, calibrated, onCalibrate, onAcquire }: Props) {
  const [calType, setCalType] = useState<'mono_exponential' | 'bi_exponential'>('mono_exponential')
  const [tau, setTau] = useState(4)
  const [gateWidth, setGateWidth] = useState<'short' | 'medium' | 'long'>('medium')

  const [integrationTime, setIntegrationTime] = useState(200)
  const [subsampling, setSubsampling] = useState(1)
  const [outputFormat, setOutputFormat] = useState<'image' | 'raw'>('image')

  const calibrate = () => {
    onCalibrate({ calibration_type: calType, expected_tau_ns: tau, gate_width: gateWidth })
  }
  const acquire = () => {
    onAcquire({
      integration_time_ms: integrationTime,
      gate_subsampling: subsampling,
      output_format: outputFormat,
    })
  }

  return (
    <div className="panel">
      <h2>FLIM</h2>

      <h3>IRF calibration {calibrated ? '✓' : ''}</h3>
      <label>
        Decay model
        <select value={calType} onChange={(e) => setCalType(e.target.value as typeof calType)}>
          <option value="mono_exponential">Mono-exponential</option>
          <option value="bi_exponential">Bi-exponential</option>
        </select>
      </label>
      <label>
        Expected τ (ns)
        <input type="number" min={0.1} step={0.1} value={tau} onChange={(e) => setTau(Number(e.target.value))} />
      </label>
      <label>
        Gate width
        <select value={gateWidth} onChange={(e) => setGateWidth(e.target.value as typeof gateWidth)}>
          <option value="short">Short</option>
          <option value="medium">Medium</option>
          <option value="long">Long</option>
        </select>
      </label>
      <button type="button" disabled={disabled} onClick={calibrate}>
        Calibrate IRF
      </button>

      <h3>Acquisition</h3>
      <label>
        Integration time (ms)
        <input
          type="number"
          min={1}
          value={integrationTime}
          onChange={(e) => setIntegrationTime(Number(e.target.value))}
        />
      </label>
      <label>
        Gate subsampling
        <input
          type="number"
          min={1}
          value={subsampling}
          onChange={(e) => setSubsampling(Number(e.target.value))}
        />
      </label>
      <label>
        Output
        <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as typeof outputFormat)}>
          <option value="image">Image (lifetime map)</option>
          <option value="raw">Raw</option>
        </select>
      </label>
      <button type="button" disabled={disabled} onClick={acquire}>
        {disabled ? 'Busy…' : 'Acquire FLIM'}
      </button>
    </div>
  )
}
