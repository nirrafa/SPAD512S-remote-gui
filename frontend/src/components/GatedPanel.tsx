import { useState } from 'react'
import { getOptimalParams } from '../api/client'
import type { GatedParams, SystemInfo } from '../api/types'

interface Props {
  systemInfo: SystemInfo | null
  disabled: boolean
  onAcquire: (params: GatedParams) => void
}

const GATED_BIT_DEPTHS = [6, 7, 8, 9, 10, 11, 12]

export function GatedPanel({ systemInfo, disabled, onAcquire }: Props) {
  const [bitDepth, setBitDepth] = useState(8)
  const [integrationTime, setIntegrationTime] = useState(100)
  const [iterations, setIterations] = useState(1)
  const [gateSteps, setGateSteps] = useState(20)
  const [stepSize, setStepSize] = useState(18)
  const [gateWidth, setGateWidth] = useState(5)
  const [gateOffset, setGateOffset] = useState(0)
  const [direction, setDirection] = useState<'forward' | 'reverse'>('forward')
  const [trigger, setTrigger] = useState<'internal' | 'external'>('external')
  const [overlap, setOverlap] = useState(false)
  const [stream, setStream] = useState(false)
  const [pileup, setPileup] = useState(false)
  const [arbitrary, setArbitrary] = useState('')

  const bitDepths = systemInfo?.valid_bit_depths.filter((b) => b >= 6) ?? GATED_BIT_DEPTHS

  const fillOptimal = async () => {
    const opt = await getOptimalParams()
    setGateSteps(opt.steps)
    setStepSize(opt.min_step)
    setGateOffset(opt.offset)
  }

  const parseArbitrary = (): number[] | undefined => {
    const parts = arbitrary
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .map(Number)
      .filter((n) => !Number.isNaN(n))
    return parts.length > 0 ? parts : undefined
  }

  const submit = () => {
    onAcquire({
      bit_depth: bitDepth,
      integration_time_ms: integrationTime,
      iterations,
      gate_steps: gateSteps,
      gate_step_size_ps: stepSize,
      gate_width: gateWidth,
      gate_offset: gateOffset,
      gate_direction: direction,
      gate_trigger_source: trigger,
      overlap,
      stream,
      pileup_correction: pileup,
      arbitrary_steps: parseArbitrary(),
    })
  }

  return (
    <div className="panel">
      <h2>Gated acquisition</h2>
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
        Integration time (ms)
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
        Gate steps
        <input
          type="number"
          min={1}
          value={gateSteps}
          onChange={(e) => setGateSteps(Number(e.target.value))}
        />
      </label>
      <label>
        Gate step size (ps)
        <input
          type="number"
          min={1}
          value={stepSize}
          onChange={(e) => setStepSize(Number(e.target.value))}
        />
      </label>
      <label>
        Gate width (ns)
        <input
          type="number"
          min={1}
          value={gateWidth}
          onChange={(e) => setGateWidth(Number(e.target.value))}
        />
      </label>
      <label>
        Gate offset (ps)
        <input
          type="number"
          value={gateOffset}
          onChange={(e) => setGateOffset(Number(e.target.value))}
        />
      </label>
      <label>
        Direction
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value as 'forward' | 'reverse')}
        >
          <option value="forward">forward</option>
          <option value="reverse">reverse</option>
        </select>
      </label>
      <label>
        Trigger source
        <select
          value={trigger}
          onChange={(e) => setTrigger(e.target.value as 'internal' | 'external')}
        >
          <option value="external">external</option>
          <option value="internal">internal</option>
        </select>
      </label>
      <label>
        Arbitrary steps (comma-separated, overrides gate steps)
        <input
          type="text"
          placeholder="e.g. 0, 5, 10, 20, 50"
          value={arbitrary}
          onChange={(e) => setArbitrary(e.target.value)}
        />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={overlap} onChange={(e) => setOverlap(e.target.checked)} />
        Read/exposure overlap
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={stream} onChange={(e) => setStream(e.target.checked)} />
        Streaming
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={pileup} onChange={(e) => setPileup(e.target.checked)} />
        Pileup correction
      </label>
      <button type="button" onClick={() => void fillOptimal()} disabled={disabled}>
        Auto-fill optimal
      </button>
      <button type="button" onClick={submit} disabled={disabled}>
        {disabled ? 'Busy…' : 'Acquire'}
      </button>
    </div>
  )
}
