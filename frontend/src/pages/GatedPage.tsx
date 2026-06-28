import { useEffect, useState } from 'react'
import { acquireGated, getStatus, getSystemInfo } from '../api/client'
import type { AcquireResult, GatedParams, SystemInfo } from '../api/types'
import { GateStepSlider } from '../components/GateStepSlider'
import { GatedPanel } from '../components/GatedPanel'
import { ImageCanvas } from '../components/ImageCanvas'
import { ProgressBar } from '../components/ProgressBar'
import { StatusBanner } from '../components/StatusBanner'
import { useWebSocket } from '../hooks/useWebSocket'
import { COLORMAP_NAMES, type ColormapName } from '../utils/colormap'

export function GatedPage() {
  const live = useWebSocket()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [vendorConnected, setVendorConnected] = useState(false)
  const [colormap, setColormap] = useState<ColormapName>('viridis')
  const [step, setStep] = useState(0)
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
  const stepCount = live.stepCount || (result?.total_gate_steps ?? 0)
  const clampedStep = Math.min(step, Math.max(stepCount - 1, 0))
  const preview = live.stepPreviews[clampedStep] ?? result?.preview ?? null

  const onAcquire = async (params: GatedParams) => {
    setAcquiring(true)
    setError(null)
    setStep(0)
    try {
      const res = await acquireGated(params)
      setResult(res)
      if (res.status === 'error' || res.status === 'busy') setError(res.message ?? res.status)
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
        <GatedPanel
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
          <GateStepSlider count={stepCount} value={clampedStep} onChange={setStep} />
          <ImageCanvas preview={preview} colormap={colormap} />
        </section>
      </div>
    </main>
  )
}
