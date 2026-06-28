import { useEffect, useRef, useState } from 'react'
import type { Preview } from '../api/types'
import { applyColormap, decodeBase64, type ColormapName } from '../utils/colormap'

interface Props {
  preview: Preview | null
  colormap: ColormapName
}

const DISPLAY = 512

export function ImageCanvas({ preview, colormap }: Props) {
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

    const values = decodeBase64(preview.data)
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
  }, [preview, colormap, scale, offset])

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
      <canvas
        ref={canvasRef}
        width={DISPLAY}
        height={DISPLAY}
        onWheel={onWheel}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={onUp}
      />
      <div className="canvas-controls">
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
