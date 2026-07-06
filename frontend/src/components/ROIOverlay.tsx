import { useRef, useState } from 'react'
import type { Point, Roi } from '../utils/imageProcessing'
import type { RoiMode } from '../hooks/useROI'

interface Props {
  size: number
  mode: RoiMode
  rois: Roi[]
  onAddRectangle: (x: number, y: number, width: number, height: number) => void
  onAddFreehand: (points: Point[]) => void
  onRemove: (id: string) => void
}

interface DraftRect {
  x0: number
  y0: number
  x1: number
  y1: number
}

const MIN_AREA = 9

export function ROIOverlay({ size, mode, rois, onAddRectangle, onAddFreehand, onRemove }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [rect, setRect] = useState<DraftRect | null>(null)
  const [path, setPath] = useState<Point[]>([])
  const drawing = useRef(false)

  const toLocal = (e: React.MouseEvent): Point => {
    const box = svgRef.current?.getBoundingClientRect()
    if (!box) return [0, 0]
    const scale = size / box.width
    return [(e.clientX - box.left) * scale, (e.clientY - box.top) * scale]
  }

  const onDown = (e: React.MouseEvent) => {
    if (mode === 'none') return
    drawing.current = true
    const [x, y] = toLocal(e)
    if (mode === 'rectangle') setRect({ x0: x, y0: y, x1: x, y1: y })
    else setPath([[x, y]])
  }

  const onMove = (e: React.MouseEvent) => {
    if (!drawing.current) return
    const [x, y] = toLocal(e)
    if (mode === 'rectangle') setRect((r) => (r ? { ...r, x1: x, y1: y } : r))
    else setPath((p) => [...p, [x, y]])
  }

  const onUp = () => {
    if (!drawing.current) return
    drawing.current = false
    if (mode === 'rectangle' && rect) {
      const x = Math.min(rect.x0, rect.x1)
      const y = Math.min(rect.y0, rect.y1)
      const width = Math.abs(rect.x1 - rect.x0)
      const height = Math.abs(rect.y1 - rect.y0)
      if (width * height >= MIN_AREA) onAddRectangle(x, y, width, height)
    } else if (mode === 'freehand' && path.length >= 3) {
      onAddFreehand(path)
    }
    setRect(null)
    setPath([])
  }

  return (
    <svg
      ref={svgRef}
      className="roi-overlay"
      viewBox={`0 0 ${size} ${size}`}
      style={{ pointerEvents: mode === 'none' ? 'none' : 'auto' }}
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={onUp}
      onMouseLeave={onUp}
    >
      {rois.map((roi) => {
        const [cx, cy] =
          roi.type === 'rectangle'
            ? [roi.x + 4, roi.y + 12]
            : [(roi.points[0]?.[0] ?? 0) + 4, (roi.points[0]?.[1] ?? 0) + 12]
        return (
          <g key={roi.id} className="roi">
            {roi.type === 'rectangle' ? (
              <rect x={roi.x} y={roi.y} width={roi.width} height={roi.height} />
            ) : (
              <polygon points={roi.points.map(([x, y]) => `${x},${y}`).join(' ')} />
            )}
            <text x={cx} y={cy}>
              {roi.label}
            </text>
            <circle
              className="roi-remove"
              cx={roi.type === 'rectangle' ? roi.x + roi.width : (roi.points[0]?.[0] ?? 0)}
              cy={roi.type === 'rectangle' ? roi.y : (roi.points[0]?.[1] ?? 0)}
              r={7}
              onMouseDown={(e) => {
                e.stopPropagation()
                onRemove(roi.id)
              }}
            />
          </g>
        )
      })}
      {rect && (
        <rect
          className="roi-draft"
          x={Math.min(rect.x0, rect.x1)}
          y={Math.min(rect.y0, rect.y1)}
          width={Math.abs(rect.x1 - rect.x0)}
          height={Math.abs(rect.y1 - rect.y0)}
        />
      )}
      {path.length > 1 && (
        <polyline className="roi-draft" points={path.map(([x, y]) => `${x},${y}`).join(' ')} />
      )}
    </svg>
  )
}
