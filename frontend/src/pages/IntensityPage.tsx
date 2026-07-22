import { useEffect, useMemo, useState } from 'react'
import { getStatus, getSystemInfo } from '../api/client'
import type { IntensityParams, SystemInfo } from '../api/types'
import { ImageCanvas } from '../components/ImageCanvas'
import { IntensityPanel } from '../components/IntensityPanel'
import { PixelHistogram } from '../components/PixelHistogram'
import { ProgressBar } from '../components/ProgressBar'
import { ROIOverlay } from '../components/ROIOverlay'
import { RoiStatsTable } from '../components/RoiStatsTable'
import { StatusBanner } from '../components/StatusBanner'
import { WBRangeControl } from '../components/WBRangeControl'
import { useAcquisition } from '../hooks/useAcquisition'
import { useROI, type RoiMode } from '../hooks/useROI'
import { useWebSocket } from '../hooks/useWebSocket'
import { COLORMAP_NAMES, decodeBase64, type ColormapName } from '../utils/colormap'
import { roiStats, scaleRoi, type IntensityRange } from '../utils/imageProcessing'

const DISPLAY = 512

export function IntensityPage() {
  const live = useWebSocket()
  const acq = useAcquisition()
  const roi = useROI()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [vendorConnected, setVendorConnected] = useState(false)
  const [colormap, setColormap] = useState<ColormapName>('viridis')
  const [roiMode, setRoiMode] = useState<RoiMode>('none')
  const [range, setRange] = useState<IntensityRange | null>(null)

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
  const values = useMemo(() => (preview ? decodeBase64(preview.data) : null), [preview])

  const statRows = useMemo(() => {
    if (!preview || !values) return []
    const sx = preview.width / DISPLAY
    const sy = preview.height / DISPLAY
    return roi.rois.map((r) => ({
      roi: r,
      stats: roiStats(values, preview.width, preview.height, scaleRoi(r, sx, sy)),
    }))
  }, [roi.rois, preview, values])

  const onAcquire = (params: IntensityParams) => {
    setRange(null)
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
            <WBRangeControl range={range} onChange={setRange} values={values} />
            {roi.rois.length > 0 && (
              <button type="button" className="link" onClick={roi.clear}>
                clear ROIs
              </button>
            )}
            {acq.lastResult?.dark_corrected && <span className="ok">dark-corrected</span>}
            {acq.lastResult?.host_path && (
              <span className="muted">saved: {acq.lastResult.host_path}</span>
            )}
          </div>
          <ProgressBar value={live.progress} visible={busy} />
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
          <h3>ROI statistics</h3>
          <RoiStatsTable rows={statRows} onRemove={roi.remove} />
          <h3>Pixel histogram</h3>
          <PixelHistogram values={values} />
        </section>
      </div>
    </main>
  )
}
