import { useState } from 'react'
import './App.css'
import { CalibrationPage } from './pages/CalibrationPage'
import { ExperimentLogPage } from './pages/ExperimentLogPage'
import { FLIMPage } from './pages/FLIMPage'
import { GatedPage } from './pages/GatedPage'
import { HealthPage } from './pages/HealthPage'
import { IntensityPage } from './pages/IntensityPage'
import { LivePage } from './pages/LivePage'
import { QueuePage } from './pages/QueuePage'
import { Raw1BitPage } from './pages/Raw1BitPage'
import { SweepPage } from './pages/SweepPage'

type Mode =
  | 'intensity'
  | 'gated'
  | 'flim'
  | 'raw1bit'
  | 'live'
  | 'queue'
  | 'sweep'
  | 'calibration'
  | 'health'
  | 'log'

function App() {
  const [mode, setMode] = useState<Mode>('intensity')
  return (
    <>
      <nav className="tabs">
        <button
          type="button"
          className={mode === 'intensity' ? 'active' : ''}
          onClick={() => setMode('intensity')}
        >
          Intensity
        </button>
        <button
          type="button"
          className={mode === 'gated' ? 'active' : ''}
          onClick={() => setMode('gated')}
        >
          Gated
        </button>
        <button
          type="button"
          className={mode === 'flim' ? 'active' : ''}
          onClick={() => setMode('flim')}
        >
          FLIM
        </button>
        <button
          type="button"
          className={mode === 'raw1bit' ? 'active' : ''}
          onClick={() => setMode('raw1bit')}
        >
          Raw 1-bit
        </button>
        <button
          type="button"
          className={mode === 'live' ? 'active' : ''}
          onClick={() => setMode('live')}
        >
          Live
        </button>
        <button
          type="button"
          className={mode === 'queue' ? 'active' : ''}
          onClick={() => setMode('queue')}
        >
          Queue
        </button>
        <button
          type="button"
          className={mode === 'sweep' ? 'active' : ''}
          onClick={() => setMode('sweep')}
        >
          Sweep
        </button>
        <button
          type="button"
          className={mode === 'calibration' ? 'active' : ''}
          onClick={() => setMode('calibration')}
        >
          Calibration
        </button>
        <button
          type="button"
          className={mode === 'health' ? 'active' : ''}
          onClick={() => setMode('health')}
        >
          Health
        </button>
        <button
          type="button"
          className={mode === 'log' ? 'active' : ''}
          onClick={() => setMode('log')}
        >
          Log
        </button>
      </nav>
      {mode === 'intensity' && <IntensityPage />}
      {mode === 'gated' && <GatedPage />}
      {mode === 'flim' && <FLIMPage />}
      {mode === 'raw1bit' && <Raw1BitPage />}
      {mode === 'live' && <LivePage />}
      {mode === 'queue' && <QueuePage />}
      {mode === 'sweep' && <SweepPage />}
      {mode === 'calibration' && <CalibrationPage />}
      {mode === 'health' && <HealthPage />}
      {mode === 'log' && <ExperimentLogPage />}
    </>
  )
}

export default App
