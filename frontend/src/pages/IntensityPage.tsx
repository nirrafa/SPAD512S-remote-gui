import { useEffect, useState } from 'react'
import { getStatus, getSystemInfo } from '../api/client'
import type { IntensityParams, SystemInfo } from '../api/types'
import { ImageCanvas } from '../components/ImageCanvas'
import { IntensityPanel } from '../components/IntensityPanel'
import { ProgressBar } from '../components/ProgressBar'
import { StatusBanner } from '../components/StatusBanner'
import { useAcquisition } from '../hooks/useAcquisition'
import { useWebSocket } from '../hooks/useWebSocket'
import { COLORMAP_NAMES, type ColormapName } from '../utils/colormap'

export function IntensityPage() {
  const live = useWebSocket()
  const acq = useAcquisition()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [vendorConnected, setVendorConnected] = useState(false)
  const [colormap, setColormap] = useState<ColormapName>('viridis')

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
    getSystemInfo()
      .then(setSystemInfo)
      .catch(() => setSystemInfo(null))
  }, [live.wsConnected])

  const busy = live.busy || acq.acquiring
  const preview = live.preview ?? acq.preview

  const onAcquire = (params: IntensityParams) => {
    void acq.acquire(params)
  }

  return (
    <main className="app">
      <header>
        <h1>SPAD512² Remote Control</h1>
        <StatusBanner
          vendorConnected={vendorConnected}
          wsConnected={live.wsConnected}
          busy={busy}
          error={acq.error}
        />
      </header>

      <div className="layout">
        <IntensityPanel
          systemInfo={systemInfo}
          disabled={busy || !vendorConnected}
          onAcquire={onAcquire}
        />

        <section className="viewer">
          {acq.lastResult?.warning && <p className="warning">⚠ {acq.lastResult.warning}</p>}
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
            {acq.lastResult?.host_path && (
              <span className="muted">saved: {acq.lastResult.host_path}</span>
            )}
          </div>
          <ProgressBar value={live.progress} visible={busy} />
          <ImageCanvas preview={preview} colormap={colormap} />
        </section>
      </div>
    </main>
  )
}
