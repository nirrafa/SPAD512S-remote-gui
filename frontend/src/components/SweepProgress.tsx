import type { SweepResult } from '../api/types'

interface Props {
  result: SweepResult | null
  running: boolean
}

export function SweepProgress({ result, running }: Props) {
  if (!result && !running) return null
  return (
    <div className="panel">
      <h2>Sweep progress</h2>
      {running && <p className="muted">Sweep running…</p>}
      {result && (
        <>
          <p>
            {result.status === 'done'
              ? `Completed ${result.points_completed ?? 0} point(s)`
              : result.status === 'error'
                ? `Failed: ${result.message ?? 'unknown error'}`
                : 'Running in background'}
            {result.points_skipped ? ` (${result.points_skipped} resumed/skipped)` : ''}
          </p>
          {result.results && result.results.length > 0 && (
            <table className="sweep-results">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Point</th>
                  <th>Saved to</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((point) => (
                  <tr key={point.index}>
                    <td>{point.index + 1}</td>
                    <td>{point.label}</td>
                    <td className="muted">{point.host_path ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
