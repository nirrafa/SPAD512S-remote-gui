import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Preview } from '../api/types'
import { applyColormap, decodeBase64, type ColormapName } from '../utils/colormap'
import { stretchValues, type IntensityRange } from '../utils/imageProcessing'

interface Props {
  preview: Preview | null
  colormap: ColormapName
  id?: string
  range?: IntensityRange | null
  overlay?: ReactNode
  onViewport?: (viewport: { scale: number; x: number; y: number }) => void
}

const DISPLAY = 512

export function ImageCanvas({ preview, colormap, id, range, overlay, onViewport }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragRef = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.fillStyle = '#111'
    ctx.fillRect(0, 0, DISPLAY, DISPLAY)
    if (!preview) return

    const raw = decodeBase64(preview.data)
    const values = range ? stretchValues(raw, range) : raw
    const rgba = applyColormap(values, colormap)
    const imageData = new ImageData(preview.width, preview.height)
    imageData.data.set(rgba)

    const off = document.createElement('canvas')
    off.width = preview.width
    off.height = preview.height
    off.getContext('2d')?.putImageData(imageData, 0, 0)

    const base = DISPLAY / Math.max(preview.width, preview.height)
    ctx.imageSmoothingEnabled = false
    ctx.setTransform(scale, 0, 0, scale, offset.x, offset.y)
    ctx.drawImage(off, 0, 0, preview.width * base, preview.height * base)
  }, [preview, colormap, scale, offset, range])

  useEffect(() => {
    onViewport?.({ scale, x: offset.x, y: offset.y })
  }, [scale, offset, onViewport])

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    setScale((s) => Math.min(Math.max(s * (e.deltaY < 0 ? 1.1 : 0.9), 0.25), 16))
  }
  const onDown = (e: React.MouseEvent) => {
    dragRef.current = { x: e.clientX - offset.x, y: e.clientY - offset.y }
  }
  const onMove = (e: React.MouseEvent) => {
    if (!dragRef.current) return
    setOffset({ x: e.clientX - dragRef.current.x, y: e.clientY - dragRef.current.y })
  }
  const onUp = () => {
    dragRef.current = null
  }
  const reset = () => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }

  return (
    <div className="image-canvas">
      <div className="image-canvas-stage">
        <canvas
          id={id}
          ref={canvasRef}
          width={DISPLAY}
          height={DISPLAY}
          onWheel={onWheel}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onUp}
        />
        {overlay && <div className="image-canvas-overlay">{overlay}</div>}
      </div>
      <div className="canvas-controls">
        <button type="button" onClick={() => setScale((s) => Math.min(s * 1.25, 16))}>
          zoom in
        </button>
        <button type="button" onClick={() => setScale((s) => Math.max(s * 0.8, 0.25))}>
          zoom out
        </button>
        <button type="button" onClick={reset}>
          reset view
        </button>
        {preview && (
          <span className="muted">
            {preview.width}×{preview.height} · peak {preview.max_value}
          </span>
        )}
      </div>
    </div>
  )
}
