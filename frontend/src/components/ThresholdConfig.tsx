import { useEffect, useState } from 'react'
import type { HealthConfig } from '../api/types'

interface Props {
  config: HealthConfig | null
  disabled: boolean
  onSave: (update: Partial<HealthConfig>) => void
}

export function ThresholdConfig({ config, disabled, onSave }: Props) {
  const [tempChip, setTempChip] = useState(75)
  const [vexMax, setVexMax] = useState(25)
  const [pollInterval, setPollInterval] = useState(0.5)

  useEffect(() => {
    if (config) {
      setTempChip(config.temp_threshold_chip)
      setVexMax(config.vex_max)
      setPollInterval(config.poll_interval_s)
    }
  }, [config])

  return (
    <div className="panel">
      <h2>Thresholds</h2>
      <label>
        Chip over-temperature (°C)
        <input
          type="number"
          value={tempChip}
          onChange={(e) => setTempChip(Number(e.target.value))}
        />
      </label>
      <label>
        Max excess bias (V)
        <input type="number" value={vexMax} onChange={(e) => setVexMax(Number(e.target.value))} />
      </label>
      <label>
        Poll interval (s)
        <input
          type="number"
          step={0.1}
          min={0.1}
          value={pollInterval}
          onChange={(e) => setPollInterval(Number(e.target.value))}
        />
      </label>
      <button
        type="button"
        disabled={disabled}
        onClick={() =>
          onSave({
            temp_threshold_chip: tempChip,
            vex_max: vexMax,
            poll_interval_s: pollInterval,
          })
        }
      >
        Save thresholds
      </button>
    </div>
  )
}
