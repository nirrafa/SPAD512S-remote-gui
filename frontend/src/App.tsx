import { useState } from 'react'
import './App.css'
import { CalibrationPage } from './pages/CalibrationPage'
import { FLIMPage } from './pages/FLIMPage'
import { GatedPage } from './pages/GatedPage'
import { IntensityPage } from './pages/IntensityPage'

type Mode = 'intensity' | 'gated' | 'flim' | 'calibration'

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
          className={mode === 'calibration' ? 'active' : ''}
          onClick={() => setMode('calibration')}
        >
          Calibration
        </button>
      </nav>
      {mode === 'intensity' && <IntensityPage />}
      {mode === 'gated' && <GatedPage />}
      {mode === 'flim' && <FLIMPage />}
      {mode === 'calibration' && <CalibrationPage />}
    </>
  )
}

export default App
