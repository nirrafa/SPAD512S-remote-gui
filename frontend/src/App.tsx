import { useEffect, useState } from 'react'
import './App.css'

type BridgeHealth = { status: string; version: string }

function App() {
  const [health, setHealth] = useState<BridgeHealth | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json() as Promise<BridgeHealth>)
      .then(setHealth)
      .catch((err: unknown) => setError(String(err)))
  }, [])

  return (
    <main className="app">
      <h1>SPAD512² Remote Control</h1>
      <p className="status">
        Bridge:{' '}
        {health ? (
          <span className="ok">connected (v{health.version})</span>
        ) : error ? (
          <span className="err">unavailable</span>
        ) : (
          <span>checking…</span>
        )}
      </p>
    </main>
  )
}

export default App
