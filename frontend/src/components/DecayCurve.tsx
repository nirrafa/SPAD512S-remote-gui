interface Series {
  label: string
  counts: number[]
}

interface Props {
  gateOffsets: number[]
  series: Series[]
}

const WIDTH = 380
const HEIGHT = 200
const PADDING = 36
const COLORS = ['#4f9cff', '#4caf50', '#ff9800', '#e05c8a', '#9c6ade']

export function DecayCurve({ gateOffsets, series }: Props) {
  const active = series.filter((s) => s.counts.length > 0)
  if (gateOffsets.length === 0 || active.length === 0) {
    return <p className="muted">Draw an ROI on a gated stack to see its decay curve.</p>
  }

  const maxCount = Math.max(1, ...active.flatMap((s) => s.counts))
  const n = gateOffsets.length
  const px = (i: number) => PADDING + (n === 1 ? 0 : (i / (n - 1)) * (WIDTH - 2 * PADDING))
  const py = (v: number) => HEIGHT - PADDING - (v / maxCount) * (HEIGHT - 2 * PADDING)

  return (
    <svg
      id="decay-curve"
      className="decay-curve"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="Per-ROI decay curve"
    >
      <line x1={PADDING} y1={HEIGHT - PADDING} x2={WIDTH - PADDING} y2={HEIGHT - PADDING} stroke="currentColor" />
      <line x1={PADDING} y1={PADDING} x2={PADDING} y2={HEIGHT - PADDING} stroke="currentColor" />
      {active.map((s, si) => (
        <polyline
          key={si}
          fill="none"
          stroke={COLORS[si % COLORS.length]}
          strokeWidth={1.8}
          points={s.counts.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(' ')}
        />
      ))}
      <text x={WIDTH / 2} y={HEIGHT - 6} textAnchor="middle" fontSize={11}>
        Gate offset (ps)
      </text>
      <text x={10} y={HEIGHT / 2} textAnchor="middle" fontSize={11} transform={`rotate(-90 10 ${HEIGHT / 2})`}>
        Mean counts
      </text>
    </svg>
  )
}
