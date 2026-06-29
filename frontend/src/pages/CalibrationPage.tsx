import { useEffect, useState } from 'react'
import {
  calibrateBreakdown,
  calibrateDeadPixel,
  calibrateMasterSlaveOffset,
  calibrateNoise,
  getCalibrationStatus,
  getDcrCurve,
  getStatus,
} from '../api/client'
import type { CalibrationStatus, CalibrationStepResult, DCRCurve } from '../api/types'
import { CalibrationCard } from '../components/CalibrationCard'
import { DCRCurveChart } from '../components/DCRCurveChart'
import { StatusBanner } from '../components/StatusBanner'
import { useWebSocket } from '../hooks/useWebSocket'

const SETUP_PROMPTS: Record<string, string> = {
  noise: 'Cap the objective / ensure dark conditions.',
  dead_pixel: 'Cap the objective / ensure dark conditions.',
  master_slave_offset: 'Provide uniform pulsed illumination.',
}

export function CalibrationPage() {
  const live = useWebSocket()
  const [vendorConnected, setVendorConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<CalibrationStatus | null>(null)
  const [curve, setCurve] = useState<DCRCurve | null>(null)

  const refreshStatus = () => {
    getCalibrationStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
  }

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
    refreshStatus()
  }, [live.wsConnected])

  const runStep = async (run: () => Promise<CalibrationStepResult>, fetchCurve: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const res = await run()
      if (res.status === 'error') setError(res.message ?? 'calibration failed')
      refreshStatus()
      if (fetchCurve && res.status === 'done') {
        const dcr = await getDcrCurve()
        setCurve(dcr)
      }
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const disabled = busy || !vendorConnected

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
        <section className="calibration-grid">
          <CalibrationCard
            title="Breakdown"
            entry={status?.breakdown}
            disabled={disabled}
            onRun={() => runStep(calibrateBreakdown, false)}
          />
          <CalibrationCard
            title="Noise"
            entry={status?.noise}
            setupPrompt={SETUP_PROMPTS.noise}
            disabled={disabled}
            onRun={() => runStep(calibrateNoise, true)}
          />
          <CalibrationCard
            title="Dead pixel"
            entry={status?.dead_pixel}
            setupPrompt={SETUP_PROMPTS.dead_pixel}
            disabled={disabled}
            onRun={() => runStep(calibrateDeadPixel, true)}
          />
          <CalibrationCard
            title="Master/slave offset"
            entry={status?.master_slave_offset}
            setupPrompt={SETUP_PROMPTS.master_slave_offset}
            disabled={disabled}
            onRun={() => runStep(calibrateMasterSlaveOffset, false)}
          />
          <CalibrationCard title="FLIM IRF" entry={status?.flim_irf} />
        </section>

        <section className="viewer">
          <h3>DCR curve</h3>
          <DCRCurveChart curve={curve} />
        </section>
      </div>
    </main>
  )
}
