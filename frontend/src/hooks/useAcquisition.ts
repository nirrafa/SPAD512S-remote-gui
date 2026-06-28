import { useCallback, useState } from 'react'
import { acquireIntensity } from '../api/client'
import type { AcquireResult, IntensityParams, Preview } from '../api/types'

export interface AcquisitionState {
  acquiring: boolean
  lastResult: AcquireResult | null
  error: string | null
  preview: Preview | null
  acquire: (params: IntensityParams) => Promise<void>
}

export function useAcquisition(): AcquisitionState {
  const [acquiring, setAcquiring] = useState(false)
  const [lastResult, setLastResult] = useState<AcquireResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)

  const acquire = useCallback(async (params: IntensityParams) => {
    setAcquiring(true)
    setError(null)
    try {
      const result = await acquireIntensity(params)
      setLastResult(result)
      if (result.status === 'error' || result.status === 'busy' || result.status === 'timeout') {
        setError(result.message ?? result.status)
      } else if (result.preview) {
        setPreview(result.preview) // `running` previews arrive over WebSocket
      }
    } catch (err: unknown) {
      setError(String(err))
    } finally {
      setAcquiring(false)
    }
  }, [])

  return { acquiring, lastResult, error, preview, acquire }
}
