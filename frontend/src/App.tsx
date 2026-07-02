import { useState } from 'react'
import './App.css'
import { CalibrationPage } from './pages/CalibrationPage'
import { FLIMPage } from './pages/FLIMPage'
import { GatedPage } from './pages/GatedPage'
import { HealthPage } from './pages/HealthPage'
import { IntensityPage } from './pages/IntensityPage'
import { Raw1BitPage } from './pages/Raw1BitPage'

type Mode = 'intensity' | 'gated' | 'flim' | 'raw1bit' | 'calibration' | 'health'

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
      </nav>
      {mode === 'intensity' && <IntensityPage />}
      {mode === 'gated' && <GatedPage />}
      {mode === 'flim' && <FLIMPage />}
      {mode === 'raw1bit' && <Raw1BitPage />}
      {mode === 'calibration' && <CalibrationPage />}
      {mode === 'health' && <HealthPage />}
    </>
  )
}

export default App
