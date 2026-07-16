import { useCallback, useEffect, useRef, useState } from 'react'
import { captureLiveFrame, getStatus } from '../api/client'
import type { LiveFrameResult, Preview } from '../api/types'
import { ImageCanvas } from '../components/ImageCanvas'
import { COLORMAP_NAMES, type ColormapName } from '../utils/colormap'

// Spartan by design: one frame per request, no persistence, no experiment
// log entry. The client — not the bridge — decides the cadence, so the
// single vendor socket is only ever held for the duration of one capture.
const LIVE_INTERVAL_MS = 300

export function LivePage() {
  const [vendorConnected, setVendorConnected] = useState(false)
  const [integrationTime, setIntegrationTime] = useState(20)
  const [colormap, setColormap] = useState<ColormapName>('viridis')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [live, setLive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const liveRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
  }, [])

  const captureOnce = useCallback(async (): Promise<LiveFrameResult | null> => {
    setBusy(true)
    try {
      const res = await captureLiveFrame({ integration_time: integrationTime })
      if (res.status === 'done' && res.preview) {
        setPreview(res.preview)
        setError(null)
      } else if (res.status === 'error' && res.message !== 'instrument busy') {
        setError(res.message ?? 'capture failed')
      }
      return res
    } catch (err: unknown) {
      setError(String(err))
      return null
    } finally {
      setBusy(false)
    }
  }, [integrationTime])

  const scheduleNext = useCallback(() => {
    timerRef.current = setTimeout(() => {
      void (async () => {
        if (!liveRef.current) return
        const res = await captureOnce()
        // A disconnected vendor stops the loop outright rather than
        // polling uselessly; a busy/timeout hiccup just retries next tick.
        if (res?.status === 'error' && res.message === 'vendor disconnected') {
          liveRef.current = false
          setLive(false)
          return
        }
        if (liveRef.current) scheduleNext()
      })()
    }, LIVE_INTERVAL_MS)
  }, [captureOnce])

  const toggleLive = () => {
    if (live) {
      liveRef.current = false
      setLive(false)
      if (timerRef.current) clearTimeout(timerRef.current)
    } else {
      liveRef.current = true
      setLive(true)
      scheduleNext()
    }
  }

  // Stop on tab switch / unmount — the socket must never be held when the
  // page isn't visible.
  useEffect(
    () => () => {
      liveRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  return (
    <main className="app">
      <header>
        <h1>SPAD512² Remote Control</h1>
        <div className="status-banner">
          <span className={vendorConnected ? 'ok' : 'err'}>
            vendor {vendorConnected ? 'connected' : 'disconnected'}
          </span>
          <span className={busy ? 'busy' : 'idle'}>{busy ? 'capturing' : 'idle'}</span>
          {error && <span className="err">error: {error}</span>}
        </div>
      </header>

      <div className="layout">
        <div className="panel">
          <h2>Live view</h2>
          <p className="muted">
            Spartan focus/alignment aid for hosts without the vendor GUI. Nothing is saved
            or logged.
          </p>
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
            Colormap
            <select value={colormap} onChange={(e) => setColormap(e.target.value as ColormapName)}>
              {COLORMAP_NAMES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <button type="button" disabled={!vendorConnected || live} onClick={() => void captureOnce()}>
            Capture once
          </button>
          <button type="button" disabled={!vendorConnected} onClick={toggleLive}>
            {live ? 'Stop live' : `Start live (every ${LIVE_INTERVAL_MS}ms)`}
          </button>
        </div>

        <section className="viewer">
          <ImageCanvas id="live-canvas" preview={preview} colormap={colormap} />
        </section>
      </div>
    </main>
  )
}
