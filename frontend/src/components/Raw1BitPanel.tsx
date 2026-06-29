import { useState } from 'react'
import type { Raw1BitParams, SystemInfo } from '../api/types'

interface Props {
  systemInfo: SystemInfo | null
  disabled: boolean
  onAcquire: (params: Raw1BitParams) => void
}

const FALLBACK_WIDTHS = [4, 8, 16, 32, 64, 128, 256, 512]

export function Raw1BitPanel({ systemInfo, disabled, onAcquire }: Props) {
  const [integrationTime, setIntegrationTime] = useState(100)
  const [iterations, setIterations] = useState(1)
  const [roiWidth, setRoiWidth] = useState(512)
  const [overlap, setOverlap] = useState(false)

  const widths = systemInfo?.valid_roi_widths ?? FALLBACK_WIDTHS

  const submit = () => {
    onAcquire({
      integration_time_us: integrationTime,
      iterations,
      roi_width: roiWidth,
      overlap,
    })
  }

  return (
    <div className="panel">
      <h2>Raw 1-bit acquisition</h2>
      <p className="muted">Single-photon binary frames (bit depth locked to 1).</p>
      <label>
        Integration time (µs)
        <input
          type="number"
          min={1}
          value={integrationTime}
          onChange={(e) => setIntegrationTime(Number(e.target.value))}
        />
      </label>
      <label>
        Iterations
        <input
          type="number"
          min={1}
          value={iterations}
          onChange={(e) => setIterations(Number(e.target.value))}
        />
      </label>
      <label>
        ROI width
        <select value={roiWidth} onChange={(e) => setRoiWidth(Number(e.target.value))}>
          {widths.map((w) => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={overlap} onChange={(e) => setOverlap(e.target.checked)} />
        Read/exposure overlap
      </label>
      <button type="button" disabled={disabled} onClick={submit}>
        {disabled ? 'Busy…' : 'Acquire'}
      </button>
    </div>
  )
}
