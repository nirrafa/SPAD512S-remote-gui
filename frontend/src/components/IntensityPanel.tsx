import { useState } from 'react'
import type { IntensityParams, SystemInfo } from '../api/types'

interface Props {
  systemInfo: SystemInfo | null
  disabled: boolean
  onAcquire: (params: IntensityParams) => void
}

const FALLBACK_BIT_DEPTHS = [1, 4, 6, 7, 8, 9, 10, 11, 12]
const FALLBACK_WIDTHS = [4, 8, 16, 32, 64, 128, 256, 512]

export function IntensityPanel({ systemInfo, disabled, onAcquire }: Props) {
  const [bitDepth, setBitDepth] = useState(8)
  const [integrationTime, setIntegrationTime] = useState(100)
  const [iterations, setIterations] = useState(1)
  const [roiWidth, setRoiWidth] = useState(512)
  const [overlap, setOverlap] = useState(false)
  const [pileup, setPileup] = useState(false)

  const bitDepths = systemInfo?.valid_bit_depths ?? FALLBACK_BIT_DEPTHS
  const widths = systemInfo?.valid_roi_widths ?? FALLBACK_WIDTHS
  const unit = bitDepth === 1 || bitDepth === 4 ? 'µs' : 'ms'

  const submit = () => {
    onAcquire({
      bit_depth: bitDepth,
      integration_time: integrationTime,
      iterations,
      roi_width: roiWidth,
      overlap,
      pileup_correction: pileup,
    })
  }

  return (
    <div className="panel">
      <h2>Intensity acquisition</h2>
      <label>
        Bit depth
        <select value={bitDepth} onChange={(e) => setBitDepth(Number(e.target.value))}>
          {bitDepths.map((b) => (
            <option key={b} value={b}>
              {b}-bit
            </option>
          ))}
        </select>
      </label>
      <label>
        Integration time ({unit})
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
      <label className="checkbox">
        <input type="checkbox" checked={pileup} onChange={(e) => setPileup(e.target.checked)} />
        Pileup correction
      </label>
      <button type="button" disabled={disabled} onClick={submit}>
        {disabled ? 'Busy…' : 'Acquire'}
      </button>
    </div>
  )
}
