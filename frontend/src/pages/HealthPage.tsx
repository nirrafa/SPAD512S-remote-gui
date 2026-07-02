import { useCallback, useEffect, useState } from 'react'
import {
  getHealthConfig,
  getHealthReadings,
  getStatus,
  setVex,
  updateHealthConfig,
} from '../api/client'
import type { HealthConfig, HealthReadings } from '../api/types'
import { AlarmBanner } from '../components/AlarmBanner'
import { StatusBanner } from '../components/StatusBanner'
import { TemperatureGauge } from '../components/TemperatureGauge'
import { ThresholdConfig } from '../components/ThresholdConfig'
import { useWebSocket } from '../hooks/useWebSocket'

const REFRESH_MS = 1000

export function HealthPage() {
  const live = useWebSocket()
  const [vendorConnected, setVendorConnected] = useState(false)
  const [readings, setReadings] = useState<HealthReadings | null>(null)
  const [config, setConfig] = useState<HealthConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [vexInput, setVexInput] = useState(5)
  const [vexNotice, setVexNotice] = useState<string | null>(null)

  const refresh = useCallback(() => {
    getHealthReadings()
      .then(setReadings)
      .catch(() => setError('failed to read health'))
  }, [])

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
    getHealthConfig().then(setConfig).catch(() => undefined)
    refresh()
    const id = window.setInterval(refresh, REFRESH_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  const saveConfig = async (update: Partial<HealthConfig>) => {
    await updateHealthConfig(update)
    const next = await getHealthConfig()
    setConfig(next)
  }

  const applyVex = async (confirm: boolean) => {
    setVexNotice(null)
    const res = await setVex(vexInput, confirm)
    if (res.requires_confirmation) {
      setVexNotice(`Vex ${vexInput} V exceeds the safe max (${res.vex_max} V). Confirm to apply.`)
      return
    }
    if (res.status === 'error') setError(res.message ?? 'failed to set Vex')
    refresh()
  }

  return (
    <main className="app">
      <header>
        <h1>SPAD512² Health</h1>
        <StatusBanner
          vendorConnected={vendorConnected}
          wsConnected={live.wsConnected}
          busy={live.busy}
          error={error}
        />
      </header>

      <div className="layout">
        <section>
          <h3>Alarms</h3>
          <AlarmBanner alarms={readings?.alarms ?? []} />

          <h3>Temperatures</h3>
          <div className="gauges">
            <TemperatureGauge label="Master FPGA" value={readings?.temp_master_fpga ?? 0} />
            <TemperatureGauge label="Slave FPGA" value={readings?.temp_slave_fpga ?? 0} />
            <TemperatureGauge label="PCB" value={readings?.temp_pcb ?? 0} />
            <TemperatureGauge
              label="Chip"
              value={readings?.temp_chip ?? 0}
              threshold={config?.temp_threshold_chip}
            />
          </div>

          <h3>Voltages &amp; clocks</h3>
          <div className="gauges">
            <TemperatureGauge label="Vq" value={readings?.vq ?? 0} unit=" V" />
            <TemperatureGauge
              label="Vex"
              value={readings?.vex ?? 0}
              unit=" V"
              threshold={config?.vex_max}
            />
            <TemperatureGauge
              label="Laser"
              value={(readings?.laser_frequency_hz ?? 0) / 1e6}
              unit=" MHz"
            />
            <TemperatureGauge label="Frame" value={readings?.frame_frequency_hz ?? 0} unit=" Hz" />
          </div>
          <p className={readings?.cooling_active ? 'ok' : 'err'}>
            cooling {readings?.cooling_active ? 'active' : 'inactive'}
          </p>
        </section>

        <section>
          <ThresholdConfig config={config} disabled={!vendorConnected} onSave={saveConfig} />

          <div className="panel">
            <h2>Set excess bias</h2>
            <label>
              Vex (V)
              <input
                type="number"
                value={vexInput}
                onChange={(e) => setVexInput(Number(e.target.value))}
              />
            </label>
            <button type="button" disabled={!vendorConnected} onClick={() => applyVex(false)}>
              Set Vex
            </button>
            {vexNotice && (
              <div className="vex-notice">
                <p>{vexNotice}</p>
                <button type="button" onClick={() => applyVex(true)}>
                  Confirm high Vex
                </button>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}
