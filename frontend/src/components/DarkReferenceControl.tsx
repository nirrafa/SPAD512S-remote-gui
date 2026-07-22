import { useCallback, useEffect, useState } from 'react'
import { listDarkReferences, measureDarkReference } from '../api/client'
import type { DarkReference } from '../api/types'

interface Props {
  mode: 'gated' | 'intensity'
  disabled: boolean
  buildParams: () => Record<string, unknown>
  value: string
  onChange: (id: string) => void
}

function refLabel(ref: DarkReference): string {
  const fp = ref.fingerprint
  const when = new Date(ref.created_at * 1000).toISOString().slice(5, 16).replace('T', ' ')
  if (ref.mode === 'gated') {
    return `${ref.gate_steps} steps × ${fp.gate_step_size}ps, w=${fp.gate_width}ns · ${when}`
  }
  return `${fp.bit_depth}-bit, ${fp.integration_time}ms, ${fp.roi_width}px · ${when}`
}

export function DarkReferenceControl({ mode, disabled, buildParams, value, onChange }: Props) {
  const [refs, setRefs] = useState<DarkReference[]>([])
  const [measuring, setMeasuring] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(() => {
    listDarkReferences(mode)
      .then((res) => setRefs(res.references))
      .catch(() => setRefs([]))
  }, [mode])

  useEffect(() => {
    refresh()
  }, [refresh])

  const measure = async () => {
    setMeasuring(true)
    setMessage(null)
    try {
      const { dark_reference_id: _unused, ...params } = buildParams()
      const res = await measureDarkReference(mode, params)
      if (res.status === 'done' && res.reference_id) {
        setMessage(`Dark reference stored (${res.method}).`)
        onChange(res.reference_id)
        refresh()
      } else {
        setMessage(res.message ?? 'dark reference failed')
      }
    } catch (err: unknown) {
      setMessage(String(err))
    } finally {
      setMeasuring(false)
    }
  }

  return (
    <div className="dark-ref">
      <h3>Dark-count correction</h3>
      <p className="muted">
        Cap the sensor, then measure a dark reference at the settings above. Selecting one
        subtracts it from the next acquisitions (display only — raw data stays untouched).
      </p>
      <label>
        Dark reference
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">— none (no correction) —</option>
          {refs.map((r) => (
            <option key={r.id} value={r.id}>
              {refLabel(r)}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={() => void measure()} disabled={disabled || measuring}>
        {measuring ? 'Measuring dark…' : 'Measure dark reference (cap sensor)'}
      </button>
      {message && <p className="muted">{message}</p>}
    </div>
  )
}
