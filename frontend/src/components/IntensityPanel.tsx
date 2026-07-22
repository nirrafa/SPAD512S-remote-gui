import { useState } from 'react'
import type { IntensityParams, SystemInfo } from '../api/types'
import { DarkReferenceControl } from './DarkReferenceControl'
import { PresetSelector } from './PresetSelector'

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
  const [runReducer, setRunReducer] = useState(true)
  const [darkRefId, setDarkRefId] = useState('')

  const bitDepths = systemInfo?.valid_bit_depths ?? FALLBACK_BIT_DEPTHS
  const widths = systemInfo?.valid_roi_widths ?? FALLBACK_WIDTHS
  const unit = bitDepth === 1 || bitDepth === 4 ? 'µs' : 'ms'

  const currentParams: IntensityParams = {
    bit_depth: bitDepth,
    integration_time: integrationTime,
    iterations,
    roi_width: roiWidth,
    overlap,
    pileup_correction: pileup,
    run_reducer: runReducer,
    dark_reference_id: darkRefId || undefined,
  }

  const submit = () => onAcquire(currentParams)

  const applyPreset = (params: Record<string, unknown>) => {
    if (typeof params.bit_depth === 'number') setBitDepth(params.bit_depth)
    const it = params.integration_time ?? params.integration_time_ms
    if (typeof it === 'number') setIntegrationTime(it)
    if (typeof params.iterations === 'number') setIterations(params.iterations)
    if (typeof params.roi_width === 'number') setRoiWidth(params.roi_width)
    if (typeof params.overlap === 'boolean') setOverlap(params.overlap)
    if (typeof params.pileup_correction === 'boolean') setPileup(params.pileup_correction)
    if (typeof params.run_reducer === 'boolean') setRunReducer(params.run_reducer)
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
      <label className="checkbox">
        <input
          type="checkbox"
          checked={runReducer}
          onChange={(e) => setRunReducer(e.target.checked)}
        />
        Run reducer (analysis-ready .npy)
      </label>
      <DarkReferenceControl
        mode="intensity"
        disabled={disabled}
        buildParams={() => currentParams as unknown as Record<string, unknown>}
        value={darkRefId}
        onChange={setDarkRefId}
      />
      <button type="button" disabled={disabled} onClick={submit}>
        {disabled ? 'Busy…' : 'Acquire'}
      </button>
      <PresetSelector
        mode="intensity"
        currentParams={currentParams as unknown as Record<string, unknown>}
        onLoad={applyPreset}
      />
    </div>
  )
}
