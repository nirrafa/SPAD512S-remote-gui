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
  const counter = useRef(0)
  const nextId = () => `roi-${(counter.current += 1)}`

  const addRectangle = useCallback((x: number, y: number, width: number, height: number) => {
    setRois((prev) => [
      ...prev,
      { id: nextId(), type: 'rectangle', label: roiLabel(prev.length), x, y, width, height },
    ])
  }, [])

  const addFreehand = useCallback((points: Point[]) => {
    setRois((prev) => [
      ...prev,
      { id: nextId(), type: 'freehand', label: roiLabel(prev.length), points },
    ])
  }, [])

  const remove = useCallback((id: string) => {
    setRois((prev) => prev.filter((r) => r.id !== id))
  }, [])

  const clear = useCallback(() => setRois([]), [])

  return { rois, addRectangle, addFreehand, remove, clear }
}
