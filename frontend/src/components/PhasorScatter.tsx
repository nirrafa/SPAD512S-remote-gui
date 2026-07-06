import type { PhasorData } from '../api/types'

interface Props {
  phasor: PhasorData | null
  size?: number
  id?: string
}

// Phasor scatter (g on x, s on y) over the universal semicircle g² + s² = g.
// A single-exponential decay lands on the arc; multi-exponentials fall inside.
export function PhasorScatter({ phasor, size = 260, id = 'phasor-plot' }: Props) {
  const pad = 24
  const w = size + pad * 2
  const h = size / 2 + pad * 2
  const x = (g: number) => pad + g * size
  const y = (s: number) => pad + (1 - s * 2) * (size / 2)

  const empty = !phasor || phasor.g.length === 0

  return (
    <svg id={id} className="phasor" width={w} height={h} role="img" aria-label="Phasor plot">
      <path
        d={`M ${x(0)} ${y(0)} A ${size / 2} ${size / 2} 0 0 1 ${x(1)} ${y(0)}`}
        fill="none"
        stroke="#666"
      />
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(0)} stroke="#666" />
      <text x={x(0.5)} y={h - 4} textAnchor="middle" fontSize={11}>
        g
      </text>
      <text x={6} y={y(0.25)} textAnchor="middle" fontSize={11} transform={`rotate(-90 6 ${y(0.25)})`}>
        s
      </text>
      {empty ? (
        <text x={w / 2} y={h / 2} textAnchor="middle" fontSize={11} fill="#888">
          Phasor appears after a FLIM acquisition
        </text>
      ) : (
        phasor.g.map((g, i) => (
          <circle key={i} cx={x(g)} cy={y(phasor.s[i] ?? 0)} r={1.3} fill="#4caf50" opacity={0.5} />
        ))
      )}
    </svg>
  )
}
