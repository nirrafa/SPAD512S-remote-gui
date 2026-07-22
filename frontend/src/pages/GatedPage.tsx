import { useEffect, useMemo, useState } from 'react'
import { acquireGated, getStatus, getSystemInfo } from '../api/client'
import type { AcquireResult, GatedParams, SystemInfo } from '../api/types'
import { DecayCurve } from '../components/DecayCurve'
import { GateStepSlider } from '../components/GateStepSlider'
import { GatedPanel } from '../components/GatedPanel'
import { ImageCanvas } from '../components/ImageCanvas'
import { ProgressBar } from '../components/ProgressBar'
import { ROIOverlay } from '../components/ROIOverlay'
import { StatusBanner } from '../components/StatusBanner'
import { WBRangeControl } from '../components/WBRangeControl'
import { useROI, type RoiMode } from '../hooks/useROI'
import { useWebSocket } from '../hooks/useWebSocket'
import { COLORMAP_NAMES, decodeBase64, type ColormapName } from '../utils/colormap'
import { decayFromStack, scaleRoi, type IntensityRange } from '../utils/imageProcessing'

const DISPLAY = 512

export function GatedPage() {
  const live = useWebSocket()
  const roi = useROI()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [vendorConnected, setVendorConnected] = useState(false)
  const [colormap, setColormap] = useState<ColormapName>('viridis')
  const [roiMode, setRoiMode] = useState<RoiMode>('none')
  const [step, setStep] = useState(0)
  const [acquiring, setAcquiring] = useState(false)
  const [result, setResult] = useState<AcquireResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [gateParams, setGateParams] = useState<GatedParams | null>(null)
  const [range, setRange] = useState<IntensityRange | null>(null)

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
  const previewValues = useMemo(() => (preview ? decodeBase64(preview.data) : null), [preview])

  const decodedStack = useMemo(
    () => live.stepPreviews.map((p) => (p ? decodeBase64(p.data) : null)),
    [live.stepPreviews],
  )
  const gridDims = useMemo(() => {
    const first = live.stepPreviews.find((p) => p)
    return first ? { width: first.width, height: first.height } : null
  }, [live.stepPreviews])

  const gateOffsets = useMemo(() => {
    const count = stepCount || decodedStack.length
    const base = gateParams?.gate_offset ?? 0
    const size = gateParams?.gate_step_size_ps ?? 1
    return Array.from({ length: count }, (_, i) => base + i * size)
  }, [stepCount, decodedStack.length, gateParams])

  const decaySeries = useMemo(() => {
    if (!gridDims) return []
    const sx = gridDims.width / DISPLAY
    const sy = gridDims.height / DISPLAY
    return roi.rois.map((r) => ({
      label: r.label,
      counts: decayFromStack(decodedStack, gridDims.width, gridDims.height, scaleRoi(r, sx, sy)),
    }))
  }, [roi.rois, decodedStack, gridDims])

  const onAcquire = async (params: GatedParams) => {
    setAcquiring(true)
    setError(null)
    setStep(0)
    setGateParams(params)
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
            <div className="roi-tools" role="group" aria-label="ROI tools">
              {(['none', 'rectangle', 'freehand'] as RoiMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={roiMode === m ? 'active' : ''}
                  onClick={() => setRoiMode(m)}
                >
                  {m === 'none' ? 'pan' : m}
                </button>
              ))}
            </div>
            <WBRangeControl range={range} onChange={setRange} values={previewValues} />
            {roi.rois.length > 0 && (
              <button type="button" className="link" onClick={roi.clear}>
                clear ROIs
              </button>
            )}
            {result?.dark_corrected && <span className="ok">dark-corrected</span>}
            {result?.host_path && <span className="muted">saved: {result.host_path}</span>}
          </div>
          <ProgressBar value={live.progress} visible={busy} />
          <GateStepSlider count={stepCount} value={clampedStep} onChange={setStep} />
          <ImageCanvas
            id="image-canvas"
            preview={preview}
            colormap={colormap}
            range={range}
            overlay={
              <ROIOverlay
                size={DISPLAY}
                mode={roiMode}
                rois={roi.rois}
                onAddRectangle={roi.addRectangle}
                onAddFreehand={roi.addFreehand}
                onRemove={roi.remove}
              />
            }
          />
          <h3>Decay curve</h3>
          <DecayCurve gateOffsets={gateOffsets} series={decaySeries} />
        </section>
      </div>
    </main>
  )
}
