import { useEffect, useState } from 'react'
import { acquireFlim, calibrateFlimIrf, getStatus } from '../api/client'
import type { FLIMIrfParams, FLIMParams, FLIMResult } from '../api/types'
import { FLIMPanel } from '../components/FLIMPanel'
import { ImageCanvas } from '../components/ImageCanvas'
import { PhasorScatter } from '../components/PhasorScatter'
import { StatusBanner } from '../components/StatusBanner'
import { useWebSocket } from '../hooks/useWebSocket'
import { COLORMAP_NAMES, type ColormapName } from '../utils/colormap'

export function FLIMPage() {
  const live = useWebSocket()
  const [vendorConnected, setVendorConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [calibrated, setCalibrated] = useState(false)
  const [result, setResult] = useState<FLIMResult | null>(null)
  const [colormap, setColormap] = useState<ColormapName>('viridis')

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
  }, [live.wsConnected])

  const onCalibrate = async (params: FLIMIrfParams) => {
    setBusy(true)
    setError(null)
    try {
      const res = await calibrateFlimIrf(params)
      if (res.status === 'error') setError(res.message ?? 'calibration failed')
      else setCalibrated(true)
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const onAcquire = async (params: FLIMParams) => {
    setBusy(true)
    setError(null)
    try {
      const res = await acquireFlim(params)
      setResult(res)
      if (res.status === 'error') setError(res.message ?? 'acquisition failed')
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setBusy(false)
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
        <FLIMPanel
          disabled={busy || !vendorConnected}
          calibrated={calibrated}
          onCalibrate={onCalibrate}
          onAcquire={onAcquire}
        />

        <section className="viewer">
          {result?.warning && <p className="warning">⚠ {result.warning}</p>}
          <div className="viewer-toolbar">
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
            {result?.total_gate_steps != null && (
              <span className="muted">{result.total_gate_steps} gate steps</span>
            )}
          </div>
          <h3>Lifetime map</h3>
          <ImageCanvas preview={result?.lifetime_map ?? null} colormap={colormap} />
          <h3>Phasor</h3>
          <PhasorScatter phasor={result?.phasor ?? null} />
        </section>
      </div>
    </main>
  )
}
