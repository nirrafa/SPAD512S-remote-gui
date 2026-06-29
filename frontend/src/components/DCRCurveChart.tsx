import type { DCRCurve } from '../api/types'

interface Props {
  curve: DCRCurve | null
}

const WIDTH = 360
const HEIGHT = 200
const PADDING = 32

export function DCRCurveChart({ curve }: Props) {
  if (!curve || curve.dcr_values.length === 0) {
    return <p className="muted">No DCR curve yet — run noise or dead-pixel calibration.</p>
  }

  const maxDcr = Math.max(...curve.dcr_values, 1)
  const points = curve.dcr_values.map((value, index) => {
    const x = PADDING + (index / (curve.dcr_values.length - 1)) * (WIDTH - 2 * PADDING)
    const y = HEIGHT - PADDING - (value / maxDcr) * (HEIGHT - 2 * PADDING)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  return (
    <svg
      className="dcr-chart"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="DCR versus percentage curve"
    >
      <line x1={PADDING} y1={HEIGHT - PADDING} x2={WIDTH - PADDING} y2={HEIGHT - PADDING} stroke="currentColor" />
      <line x1={PADDING} y1={PADDING} x2={PADDING} y2={HEIGHT - PADDING} stroke="currentColor" />
      <polyline fill="none" stroke="#4f9cff" strokeWidth={2} points={points.join(' ')} />
      <text x={WIDTH / 2} y={HEIGHT - 4} textAnchor="middle" fontSize={11}>
        Pixel percentage
      </text>
      <text x={10} y={HEIGHT / 2} textAnchor="middle" fontSize={11} transform={`rotate(-90 10 ${HEIGHT / 2})`}>
        DCR (counts)
      </text>
    </svg>
  )
}
