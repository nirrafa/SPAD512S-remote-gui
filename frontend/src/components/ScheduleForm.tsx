import { useState } from 'react'
import type { JobStatus, ScheduleRequest } from '../api/types'

interface Props {
  disabled: boolean
  onSchedule: (request: ScheduleRequest) => void
  job: JobStatus | null
}

export function ScheduleForm({ disabled, onSchedule, job }: Props) {
  const [startTime, setStartTime] = useState('')
  const [bitDepth, setBitDepth] = useState(8)
  const [integrationTime, setIntegrationTime] = useState(100)
  const [iterations, setIterations] = useState(1)

  const submit = () => {
    onSchedule({
      mode: 'intensity',
      params: {
        bit_depth: bitDepth,
        integration_time_ms: integrationTime,
        iterations,
      },
      start_time: startTime,
    })
  }

  return (
    <div className="panel">
      <h2>Scheduled acquisition</h2>
      <p className="muted">Queue an intensity acquisition to run unattended.</p>
      <label>
        Start time
        <input
          type="datetime-local"
          value={startTime}
          onChange={(e) => setStartTime(e.target.value)}
        />
      </label>
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
      <button type="button" disabled={disabled || !startTime} onClick={submit}>
        Schedule
      </button>
      {job && (
        <p data-testid="scheduled-job">
          Job <code>{job.job_id}</code>: {job.state}
          {job.result?.host_path && (
            <span className="muted"> → {job.result.host_path}</span>
          )}
        </p>
      )}
    </div>
  )
}
