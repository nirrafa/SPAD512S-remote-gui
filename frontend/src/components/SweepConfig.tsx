import { useState } from 'react'
import type { SweepRequest } from '../api/types'

interface Props {
  disabled: boolean
  onStart: (request: SweepRequest) => void
  onResume: () => void
}

const SWEEPABLE_PARAMS = [
  'integration_time_ms',
  'iterations',
  'gate_offset',
  'gate_width',
  'gate_steps',
]

function parseValues(spec: string): number[] {
  const trimmed = spec.trim()
  if (trimmed.includes(':')) {
    const parts = trimmed.split(':').map(Number)
    const start = parts[0] ?? Number.NaN
    const stop = parts[1] ?? Number.NaN
    const step = parts[2] ?? Number.NaN
    if ([start, stop, step].some(Number.isNaN) || step === 0) return []
    const values: number[] = []
    for (let v = start; step > 0 ? v <= stop : v >= stop; v += step) values.push(v)
    return values
  }
  return trimmed
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((v) => !Number.isNaN(v))
}

export function SweepConfig({ disabled, onStart, onResume }: Props) {
  const [mode, setMode] = useState<'intensity' | 'gated'>('intensity')
  const [parameter, setParameter] = useState('integration_time_ms')
  const [valuesSpec, setValuesSpec] = useState('50, 100, 200, 500')
  const [bitDepth, setBitDepth] = useState(8)
  const [iterations, setIterations] = useState(1)

  const values = parseValues(valuesSpec)

  const submit = () => {
    onStart({
      mode,
      sweep_parameter: parameter,
      values,
      base_params: { bit_depth: bitDepth, iterations },
    })
  }

  return (
    <div className="panel">
      <h2>Parameter sweep</h2>
      <p className="muted">
        Comma-separated list (50, 100, 200) or range start:stop:step (0:100:10).
      </p>
      <label>
        Mode
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as 'intensity' | 'gated')}
        >
          <option value="intensity">intensity</option>
          <option value="gated">gated</option>
        </select>
      </label>
      <label>
        Sweep parameter
        <select value={parameter} onChange={(e) => setParameter(e.target.value)}>
          {SWEEPABLE_PARAMS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <label>
        Values
        <input
          type="text"
          value={valuesSpec}
          onChange={(e) => setValuesSpec(e.target.value)}
        />
      </label>
      <span className="muted">{values.length} point(s)</span>
      <label>
        Bit depth
        <input
          type="number"
          min={1}
          max={12}
          value={bitDepth}
          onChange={(e) => setBitDepth(Number(e.target.value))}
        />
      </label>
      <label>
        Iterations per point
        <input
          type="number"
          min={1}
          value={iterations}
          onChange={(e) => setIterations(Number(e.target.value))}
        />
      </label>
      <button type="button" disabled={disabled || values.length === 0} onClick={submit}>
        {disabled ? 'Busy…' : 'Start sweep'}
      </button>
      <button type="button" disabled={disabled} onClick={onResume}>
        Resume last sweep
      </button>
    </div>
  )
}
