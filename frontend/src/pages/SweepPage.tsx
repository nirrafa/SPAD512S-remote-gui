import { useEffect, useRef, useState } from 'react'
import {
  acquireSweep,
  getAcquireStatus,
  getJobStatus,
  getStatus,
  resumeSweep,
  scheduleJob,
  stopAcquisition,
} from '../api/client'
import type { JobStatus, ScheduleRequest, SweepRequest, SweepResult } from '../api/types'
import { ScheduleForm } from '../components/ScheduleForm'
import { StatusBanner } from '../components/StatusBanner'
import { SweepConfig } from '../components/SweepConfig'
import { SweepProgress } from '../components/SweepProgress'
import { useWebSocket } from '../hooks/useWebSocket'

const JOB_POLL_MS = 2000

export function SweepPage() {
  const live = useWebSocket()
  const [vendorConnected, setVendorConnected] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<SweepResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const jobPoll = useRef<number | null>(null)

  useEffect(() => {
    getStatus()
      .then((s) => setVendorConnected(s.vendor_connected))
      .catch(() => setVendorConnected(false))
  }, [live.wsConnected])

  useEffect(() => {
    return () => {
      if (jobPoll.current !== null) window.clearInterval(jobPoll.current)
    }
  }, [])

  const runSweep = async (request: SweepRequest) => {
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const res = await acquireSweep(request)
      setResult(res)
      if (res.status === 'error') setError(res.message ?? 'sweep failed')
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setRunning(false)
    }
  }

  const runResume = async () => {
    setRunning(true)
    setError(null)
    try {
      const res = await resumeSweep()
      setResult(res)
      if (res.status === 'error') setError(res.message ?? 'resume failed')
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setRunning(false)
    }
  }

  const stop = async () => {
    try {
      await stopAcquisition()
      const status = await getAcquireStatus()
      setRunning(status.running)
    } catch (err: unknown) {
      setError(String(err))
    }
  }

  const schedule = async (request: ScheduleRequest) => {
    setError(null)
    try {
      const res = await scheduleJob(request)
      if (!res.job_id) {
        setError(res.message ?? 'schedule failed')
        return
      }
      const jobId = res.job_id
      const poll = async () => {
        const status = await getJobStatus(jobId).catch(() => null)
        if (status) {
          setJob(status)
          if (status.state === 'completed' || status.state === 'failed') {
            if (jobPoll.current !== null) window.clearInterval(jobPoll.current)
            jobPoll.current = null
          }
        }
      }
      if (jobPoll.current !== null) window.clearInterval(jobPoll.current)
      jobPoll.current = window.setInterval(() => void poll(), JOB_POLL_MS)
      void poll()
    } catch (err: unknown) {
      setError(String(err))
    }
  }

  const busy = live.busy || running

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
        <div>
          <SweepConfig
            disabled={busy || !vendorConnected}
            onStart={(r) => void runSweep(r)}
            onResume={() => void runResume()}
          />
          <ScheduleForm
            disabled={!vendorConnected}
            onSchedule={(r) => void schedule(r)}
            job={job}
          />
        </div>

        <section className="viewer">
          {busy && (
            <button type="button" onClick={() => void stop()}>
              Stop at safe boundary
            </button>
          )}
          <SweepProgress result={result} running={running} />
        </section>
      </div>
    </main>
  )
}
