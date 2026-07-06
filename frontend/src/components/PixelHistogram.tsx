import { useMemo } from 'react'
import { histogram } from '../utils/imageProcessing'

interface Props {
  values: Uint8Array | null
  bins?: number
}

const WIDTH = 360
const HEIGHT = 160
const PADDING = 28

export function PixelHistogram({ values, bins = 48 }: Props) {
  const hist = useMemo(() => (values ? histogram(values, bins) : null), [values, bins])

  if (!hist || hist.maxCount === 0) {
    return <p className="muted">Pixel histogram appears after an acquisition.</p>
  }

  const barWidth = (WIDTH - 2 * PADDING) / hist.counts.length
  return (
    <svg
      id="pixel-histogram"
      className="histogram"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="Pixel value histogram"
    >
      <line x1={PADDING} y1={HEIGHT - PADDING} x2={WIDTH - PADDING} y2={HEIGHT - PADDING} stroke="currentColor" />
      {hist.counts.map((c, i) => {
        const h = (c / hist.maxCount) * (HEIGHT - 2 * PADDING)
        return (
          <rect
            key={i}
            x={PADDING + i * barWidth}
            y={HEIGHT - PADDING - h}
            width={Math.max(barWidth - 0.5, 0.5)}
            height={h}
            fill="#4f9cff"
          />
        )
      })}
      <text x={WIDTH / 2} y={HEIGHT - 6} textAnchor="middle" fontSize={11}>
        Pixel value (0–255)
      </text>
    </svg>
  )
}
