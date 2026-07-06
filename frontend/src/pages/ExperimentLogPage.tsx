import { useCallback, useEffect, useState } from 'react'
import { getExperimentLog, rerunEntry } from '../api/client'
import type { ExperimentLogEntry } from '../api/types'
import { StatusBanner } from '../components/StatusBanner'
import { useWebSocket } from '../hooks/useWebSocket'

export function ExperimentLogPage() {
  const live = useWebSocket()
  const [entries, setEntries] = useState<ExperimentLogEntry[]>([])
  const [search, setSearch] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback((query: string) => {
    getExperimentLog(query ? { search: query } : undefined)
      .then((res) => setEntries(res.entries))
      .catch(() => setEntries([]))
  }, [])

  useEffect(() => {
    refresh(search)
  }, [refresh, search, live.busy])

  const onRerun = async (id: string) => {
    setBusyId(id)
    setMessage(null)
    try {
      const res = await rerunEntry(id)
      setMessage(`Re-run ${res.status}${res.host_path ? ` → ${res.host_path}` : ''}`)
      refresh(search)
    } catch (err: unknown) {
      setMessage(String(err))
    } finally {
      setBusyId(null)
    }
  }

  const rows = [...entries].reverse() // newest first for display

  return (
    <main className="app">
      <header>
        <h1>SPAD512² Remote Control</h1>
        <StatusBanner
          vendorConnected
          wsConnected={live.wsConnected}
          busy={live.busy || busyId !== null}
          error={null}
        />
      </header>

      <section className="viewer">
        <div className="viewer-toolbar">
          <label>
            Search
            <input
              type="text"
              placeholder="sample / experiment / notes"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <button type="button" onClick={() => refresh(search)}>
            refresh
          </button>
          {message && <span className="muted">{message}</span>}
        </div>

        {rows.length === 0 ? (
          <p className="muted">No acquisitions logged yet.</p>
        ) : (
          <table className="log-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Mode</th>
                <th>Sample</th>
                <th>Experiment</th>
                <th>Notes</th>
                <th>Result</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td>{e.timestamp?.replace('T', ' ').slice(0, 19) ?? '—'}</td>
                  <td>{e.mode}</td>
                  <td>{e.sample_name ?? '—'}</td>
                  <td>{e.experiment_name ?? '—'}</td>
                  <td>{e.notes ?? '—'}</td>
                  <td className="muted result-cell">{e.result_path ?? '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      disabled={busyId !== null || e.mode === 'flim'}
                      onClick={() => onRerun(e.id)}
                    >
                      re-run
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  )
}
