import type { CalibrationEntry } from '../api/types'

interface Props {
  title: string
  entry: CalibrationEntry | undefined
  setupPrompt?: string
  disabled?: boolean
  onRun?: () => void
}

function formatTimestamp(timestamp: number | undefined): string {
  if (timestamp == null) return ''
  return new Date(timestamp * 1000).toLocaleString()
}

export function CalibrationCard({ title, entry, setupPrompt, disabled, onRun }: Props) {
  const state = entry?.state ?? 'none'
  return (
    <div className="panel calibration-card">
      <h3>{title}</h3>
      <p>
        <span className={`cal-state cal-state-${state}`}>{state}</span>
        {entry?.stale && <span className="cal-stale-badge">stale</span>}
      </p>
      {state === 'done' && entry?.timestamp != null && (
        <p className="muted">Last run: {formatTimestamp(entry.timestamp)}</p>
      )}
      {setupPrompt && <p className="cal-prompt">{setupPrompt}</p>}
      {onRun && (
        <button type="button" disabled={disabled} onClick={onRun}>
          {state === 'running' ? 'Running…' : 'Run calibration'}
        </button>
      )}
    </div>
  )
}
