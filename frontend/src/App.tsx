import { useState } from 'react'
import './App.css'
import { GatedPage } from './pages/GatedPage'
import { IntensityPage } from './pages/IntensityPage'

type Mode = 'intensity' | 'gated'

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
      </nav>
      {mode === 'intensity' ? <IntensityPage /> : <GatedPage />}
    </>
  )
}

export default App
