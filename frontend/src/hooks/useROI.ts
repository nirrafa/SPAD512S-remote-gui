import { useCallback, useRef, useState } from 'react'
import type { Point, Roi } from '../utils/imageProcessing'

export type RoiMode = 'none' | 'rectangle' | 'freehand'

const roiLabel = (index: number) => String.fromCharCode(65 + (index % 26))

export interface UseROI {
  rois: Roi[]
  addRectangle: (x: number, y: number, width: number, height: number) => void
  addFreehand: (points: Point[]) => void
  remove: (id: string) => void
  clear: () => void
}

export function useROI(): UseROI {
  const [rois, setRois] = useState<Roi[]>([])
  // Monotonic so ids and labels never collide, even after a removal (deriving
  // the label from `prev.length` would recycle letters and produce two "B"s).
  const counter = useRef(0)

  const addRectangle = useCallback((x: number, y: number, width: number, height: number) => {
    const n = (counter.current += 1)
    setRois((prev) => [
      ...prev,
      { id: `roi-${n}`, type: 'rectangle', label: roiLabel(n - 1), x, y, width, height },
    ])
  }, [])

  const addFreehand = useCallback((points: Point[]) => {
    const n = (counter.current += 1)
    setRois((prev) => [...prev, { id: `roi-${n}`, type: 'freehand', label: roiLabel(n - 1), points }])
  }, [])

  const remove = useCallback((id: string) => {
    setRois((prev) => prev.filter((r) => r.id !== id))
  }, [])

  const clear = useCallback(() => setRois([]), [])

  return { rois, addRectangle, addFreehand, remove, clear }
}
