import { useCallback, useEffect, useState } from 'react'
import { getQueueStatus, runQueue, stopAcquisition } from '../api/client'
import type { QueueItemSpec, QueueStatus } from '../api/types'
import { StatusBanner } from '../components/StatusBanner'
import { useWebSocket } from '../hooks/useWebSocket'
import {
  clearQueueItems,
  loadQueueItems,
  removeQueueItem,
  updateQueueRepeat,
} from '../utils/queueStore'

function summarize(mode: string, p: Record<string, unknown>): string {
  if (mode === 'gated') {
    const bits = [
      `${p.gate_steps ?? '?'} steps × ${p.gate_step_size_ps ?? '?'}ps`,
      `w=${p.gate_width ?? '?'}ns`,
      `${p.integration_time_ms ?? p.integration_time ?? '?'}ms`,
      `${p.bit_depth ?? '?'}-bit`,
    ]
    if (typeof p.cooloff_s === 'number' && p.cooloff_s > 0) bits.push(`cool-off ${p.cooloff_s}s`)
    if (p.dark_reference_id) bits.push('dark-corrected')
    return bits.join(', ')
  }
  const bits = [
    `${p.bit_depth ?? '?'}-bit`,
    `${p.integration_time ?? p.integration_time_ms ?? '?'}ms`,
    `${p.roi_width ?? '?'}px`,
  ]
  if (p.dark_reference_id) bits.push('dark-corrected')
  return bits.join(', ')
}

export function QueuePage() {
  const live = useWebSocket()
  const [pending, setPending] = useState<QueueItemSpec[]>(loadQueueItems)
  const [status, setStatus] = useState<QueueStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const refreshStatus = useCallback(() => {
    getQueueStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [])

  useEffect(() => {
    refreshStatus()
    const timer = setInterval(refreshStatus, 2000)
    return () => clearInterval(timer)
  }, [refreshStatus])

  const totalRuns = pending.reduce((sum, item) => sum + item.repeat, 0)

  const onRun = async () => {
    setStarting(true)
    setError(null)
    try {
      const res = await runQueue(pending)
      if (res.status !== 'started') setError(res.message ?? 'could not start the queue')
      else refreshStatus()
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setStarting(false)
    }
  }

  return (
    <main className="app">
      <header>
        <h1>SPAD512² Remote Control</h1>
        <StatusBanner
          vendorConnected
          wsConnected={live.wsConnected}
          busy={live.busy || (status?.running ?? false)}
          error={error}
        />
      </header>

      <section className="viewer">
        <h2>Measurement series</h2>
        <p className="muted">
          Build a series from the Intensity / Gated tabs ("Add to queue"), press Run, and
          come back when it's done. Items run one after another; every run is saved and
          logged like a normal acquisition. Stop (safe-boundary) via the usual stop —
          remaining items are skipped.
        </p>

        <h3>Queue builder ({pending.length} items, {totalRuns} runs)</h3>
        {pending.length === 0 ? (
          <p className="muted">Empty — use "Add to queue" on a mode tab.</p>
        ) : (
          <table className="log-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Mode</th>
                <th>Settings</th>
                <th>Repeat</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {pending.map((item, index) => (
                <tr key={index}>
                  <td>{index + 1}</td>
                  <td>{item.mode}</td>
                  <td>{summarize(item.mode, item.params)}</td>
                  <td>
                    <input
                      className="repeat-input"
                      type="number"
                      min={1}
                      max={100}
                      value={item.repeat}
                      onChange={(e) => setPending(updateQueueRepeat(index, Number(e.target.value)))}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setPending(removeQueueItem(index))}
                    >
                      remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="viewer-toolbar">
          <button
            type="button"
            disabled={pending.length === 0 || starting || (status?.running ?? false)}
            onClick={() => void onRun()}
          >
            {status?.running ? 'Series running…' : `Run series (${totalRuns} runs)`}
          </button>
          {pending.length > 0 && (
            <button type="button" className="link" onClick={() => setPending(clearQueueItems())}>
              clear builder
            </button>
          )}
          {status?.running && (
            <button type="button" className="link" onClick={() => void stopAcquisition()}>
              stop series
            </button>
          )}
        </div>

        {status && status.total > 0 && (
          <>
            <h3>
              {status.running
                ? `Running: ${status.completed} / ${status.total} done`
                : `Last run: ${status.completed} / ${status.total} finished`}
            </h3>
            <table className="log-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Mode</th>
                  <th>Settings</th>
                  <th>Status</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {status.items.map((item) => (
                  <tr key={item.index}>
                    <td>{item.index + 1}</td>
                    <td>
                      {item.mode}
                      {item.dark_corrected ? ' ✓dark' : ''}
                    </td>
                    <td>{summarize(item.mode, item.params)}</td>
                    <td className={item.status === 'error' ? 'warning' : undefined}>
                      {item.status}
                      {item.message ? ` — ${item.message}` : ''}
                    </td>
                    <td className="muted result-cell">{item.host_path ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </main>
  )
}
