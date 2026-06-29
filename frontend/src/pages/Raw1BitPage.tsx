import { useEffect, useState } from 'react'
import { acquireRaw1Bit, getStatus, getSystemInfo } from '../api/client'
import type { AcquireResult, Raw1BitParams, SystemInfo } from '../api/types'
import { ImageCanvas } from '../components/ImageCanvas'
import { ProgressBar } from '../components/ProgressBar'
import { Raw1BitPanel } from '../components/Raw1BitPanel'
import { StatusBanner } from '../components/StatusBanner'
import { useWebSocket } from '../hooks/useWebSocket'
import { COLORMAP_NAMES, type ColormapName } from '../utils/colormap'

export function Raw1BitPage() {
  const live = useWebSocket()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [vendorConnected, setVendorConnected] = useState(false)
  const [colormap, setColormap] = useState<ColormapName>('viridis')
  const [acquiring, setAcquiring] = useState(false)
  const [result, setResult] = useState<AcquireResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
    getSystemInfo()
      .then(setSystemInfo)
      .catch(() => setSystemInfo(null))
  }, [live.wsConnected])

  const busy = live.busy || acquiring
  const preview = live.preview ?? result?.preview ?? null

  const onAcquire = async (params: Raw1BitParams) => {
    setAcquiring(true)
    setError(null)
    try {
      const res = await acquireRaw1Bit(params)
      setResult(res)
      if (res.status === 'error' || res.status === 'busy' || res.status === 'timeout') {
        setError(res.message ?? res.status)
      }
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setAcquiring(false)
    }
  }

  return (
    <main className="app">
      <header>
        <h1>SPAD512² Remote Control</h1>
        <StatusBanner
          vendorConnected={vendorConnected}
          wsConnected={live.wsConnected}
          busy={busy}
          error={error}
        />
      </header>

      <div className="layout">
        <Raw1BitPanel
          systemInfo={systemInfo}
          disabled={busy || !vendorConnected}
          onAcquire={(p) => void onAcquire(p)}
        />

        <section className="viewer">
          <div className="viewer-toolbar">
            <label>
              Colormap
              <select
                value={colormap}
                onChange={(e) => setColormap(e.target.value as ColormapName)}
              >
                {COLORMAP_NAMES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            {result?.host_path && <span className="muted">saved: {result.host_path}</span>}
          </div>
          <ProgressBar value={live.progress} visible={busy} />
          <ImageCanvas preview={preview} colormap={colormap} />
        </section>
      </div>
    </main>
  )
}
